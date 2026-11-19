"""Anahtar ve üyelik gerektirmeyen ücretsiz ses seçeneği (deneme/prototip için).

  * Dinleme : Mikrofon (sounddevice) + basit ses etkinliği algılama,
              metne çevirme Google'ın ücretsiz web konuşma tanıma servisiyle.
  * Konuşma : Microsoft Edge'in çevrim içi nöral sesleri (edge-tts),
              Azure ile aynı Türkçe sesler (tr-TR-EmelNeural, tr-TR-AhmetNeural).

Not: Bu iki servis resmi/ücretli API değildir; deneme için uygundur, ileride
değişebilir veya çalışmayı bırakabilir. Kalıcı ürün için Azure gibi resmi bir servis önerilir.

Kurulum:  pip install -e ".[ucretsiz]"
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor

from robot.speech.base import Dinleyici, Konusmaci

log = logging.getLogger(__name__)

ORNEKLEME = 16000
BLOK = 480  # 30 ms


def _kur_uyarisi(e: ImportError):
    return RuntimeError(f'Ücretsiz ses paketleri eksik ({e.name}). Kurmak için: pip install -e ".[ucretsiz]"')


def metne_cevir(ham_pcm: bytes, dil: str, ornekleme: int = ORNEKLEME) -> str | None:
    """16 bit mono PCM sesi Google'ın ücretsiz servisiyle metne çevirir."""
    try:
        import speech_recognition as sr
    except ImportError as e:  # pragma: no cover
        raise _kur_uyarisi(e) from e
    ses = sr.AudioData(ham_pcm, ornekleme, 2)
    try:
        return sr.Recognizer().recognize_google(ses, language=dil)
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        raise ConnectionError(f"Konuşma tanıma servisine ulaşılamadı: {e}") from e


class MikrofonDinleyici(Dinleyici):
    def __init__(self, ses_ayar, bekleme_sn: float = 15, azami_sn: float = 30):
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as e:  # pragma: no cover
            raise _kur_uyarisi(e) from e
        self._np, self._sd = np, sd
        self.dil = ses_ayar.dil
        self.hassasiyet = max(0.1, float(getattr(ses_ayar, "mikrofon_hassasiyeti", 1.0)))
        self.sessizlik_sn = ses_ayar.sessizlik_ms / 1000
        self.bekleme_sn = bekleme_sn
        self.azami_sn = azami_sn
        self._gurultu = self._ilk_gurultu = self._olc_gurultu()
        log.info("Ortam gürültüsü: %.0f, eşik: %.0f", self._gurultu, self._esik())

    def _rms(self, blok) -> float:
        return float(self._np.sqrt(self._np.mean(blok.astype(self._np.float32) ** 2)))

    def _olc_gurultu(self) -> float:
        with self._sd.InputStream(samplerate=ORNEKLEME, channels=1, dtype="int16", blocksize=BLOK) as akis:
            degerler = [self._rms(akis.read(BLOK)[0]) for _ in range(20)]  # ~0.6 sn
        return float(self._np.median(degerler))

    def _esik(self) -> float:
        return max(self._gurultu * 2.5, 120) / self.hassasiyet

    def dinle(self) -> str | None:
        esik = self._esik()
        on_kayit: deque = deque(maxlen=10)  # Konuşma başlamadan önceki 300 ms
        kayit: list = []
        konusuyor = False
        ust_uste = 0
        sessiz_sure = 0.0
        blok_sn = BLOK / ORNEKLEME
        basla = time.monotonic()
        with self._sd.InputStream(samplerate=ORNEKLEME, channels=1, dtype="int16", blocksize=BLOK) as akis:
            while True:
                blok = akis.read(BLOK)[0].copy()
                enerji = self._rms(blok)
                if not konusuyor:
                    on_kayit.append(blok)
                    ust_uste = ust_uste + 1 if enerji > esik else 0
                    if ust_uste >= 2:  # 60 ms boyunca eşiğin üstü: konuşma başladı
                        konusuyor = True
                        kayit = list(on_kayit)
                        konusma_basi = time.monotonic()
                    else:
                        # Ortam gürültüsünü çok yavaş takip et; kısık sesli konuşmayı
                        # gürültü sanıp eşiği yükseltmemek için üst sınır var.
                        self._gurultu = min(0.995 * self._gurultu + 0.005 * enerji, self._ilk_gurultu * 2)
                        esik = self._esik()
                        if time.monotonic() - basla > self.bekleme_sn:
                            return None
                    continue
                kayit.append(blok)
                # Konuşma sürerken daha düşük eşik: kelime sonlarındaki kısık sesler kesilmesin
                sessiz_sure = sessiz_sure + blok_sn if enerji < esik * 0.6 else 0.0
                if sessiz_sure >= self.sessizlik_sn or time.monotonic() - konusma_basi > self.azami_sn:
                    break
        ses = self._np.concatenate(kayit).astype(self._np.float32)
        tepe = float(self._np.max(self._np.abs(ses))) or 1.0
        # Kısık mikrofonlar için sesi yükselt (tanıma doğruluğunu artırır)
        kazanc = min(20000 / tepe, 8.0)
        ham = self._np.clip(ses * kazanc, -32768, 32767).astype(self._np.int16).tobytes()
        log.debug("Kayıt: %.1f sn, tepe %.0f, kazanç %.1f", len(ses) / ORNEKLEME, tepe, kazanc)
        return metne_cevir(ham, self.dil)


async def _sentezle(metin: str, ses_adi: str, hiz: str) -> bytes:
    import edge_tts

    veri = bytearray()
    async for parca in edge_tts.Communicate(metin, ses_adi, rate=hiz).stream():
        if parca["type"] == "audio":
            veri += parca["data"]
    return bytes(veri)


def sentezle(metin: str, ses_adi: str, hiz: str = "+0%") -> bytes:
    """Metni MP3 sese çevirir."""
    return asyncio.run(_sentezle(metin, ses_adi, hiz))


def sessizligi_kirp(veri, ornekleme: int, bas_sn: float = 0.03, son_sn: float = 0.12, esik: float = 0.01):
    """Sentezlenen sesin başındaki ve sonundaki uzun sessizliği kırpar.

    Edge sesleri her parçanın başına ~0.2 sn, sonuna ~1 sn sessizlik ekler; cümleler
    arka arkaya çalınınca bu, her noktada/virgülde yapay uzun duraklamalara yol açar.
    """
    import numpy as np

    dolu = np.where(np.abs(veri) > esik)[0]
    if len(dolu) == 0:
        return veri[:0]
    bas = max(0, dolu[0] - int(bas_sn * ornekleme))
    son = min(len(veri), dolu[-1] + int(son_sn * ornekleme))
    return veri[bas:son]


class EdgeKonusmaci(Konusmaci):
    def __init__(self, ses_ayar):
        try:
            import edge_tts  # noqa: F401
            import sounddevice as sd
            import soundfile as sf
        except ImportError as e:  # pragma: no cover
            raise _kur_uyarisi(e) from e
        self._sd, self._sf = sd, sf
        self.ses_adi = ses_ayar.ses_adi
        self.hiz = getattr(ses_ayar, "konusma_hizi", "+0%")
        self._havuz = ThreadPoolExecutor(max_workers=3, thread_name_prefix="sentez")
        self._akis = None
        self._akis_ornekleme = None

    def _hazirla_ses(self, metin: str):
        mp3 = sentezle(metin, self.ses_adi, self.hiz)
        if not mp3:
            return None, 0
        veri, ornekleme = self._sf.read(io.BytesIO(mp3), dtype="float32")
        if veri.ndim > 1:
            veri = veri.mean(axis=1)
        return sessizligi_kirp(veri, ornekleme), ornekleme

    def hazirla(self, metin: str) -> Future:
        # Sentez + çözme + kırpma arka planda: bir cümle çalarken sonrakiler hazırlanır
        return self._havuz.submit(self._hazirla_ses, metin)

    def konus(self, hazir) -> None:
        veri, ornekleme = hazir.result(timeout=30) if isinstance(hazir, Future) else self._hazirla_ses(hazir)
        if veri is None or not len(veri):
            return
        # Tek, sürekli açık çıkış akışı: cümleler arasında cihaz aç/kapa boşluğu olmaz
        if self._akis is None or self._akis_ornekleme != ornekleme:
            if self._akis is not None:
                self._akis.close()
            self._akis = self._sd.OutputStream(samplerate=ornekleme, channels=1, dtype="float32")
            self._akis.start()
            self._akis_ornekleme = ornekleme
        self._akis.write(veri.reshape(-1, 1))

    def tur_sonu(self) -> None:
        # Tampondaki son sesin de çalınmasını bekle, sonra dinlemeye geç
        if self._akis is not None:
            time.sleep(self._akis.latency + 0.05)

    def durdur(self) -> None:
        if self._akis is not None:
            self._akis.abort()
            self._akis = None

    def kapat(self) -> None:
        self._havuz.shutdown(wait=False, cancel_futures=True)
        if self._akis is not None:
            self._akis.close()
