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
        self.sessizlik_sn = ses_ayar.sessizlik_ms / 1000
        self.bekleme_sn = bekleme_sn
        self.azami_sn = azami_sn
        self._gurultu = self._olc_gurultu()
        log.info("Ortam gürültüsü: %.0f", self._gurultu)

    def _rms(self, blok) -> float:
        return float(self._np.sqrt(self._np.mean(blok.astype(self._np.float32) ** 2)))

    def _olc_gurultu(self) -> float:
        with self._sd.InputStream(samplerate=ORNEKLEME, channels=1, dtype="int16", blocksize=BLOK) as akis:
            degerler = [self._rms(akis.read(BLOK)[0]) for _ in range(20)]  # ~0.6 sn
        return float(self._np.median(degerler))

    def dinle(self) -> str | None:
        esik = max(self._gurultu * 3, 250)
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
                    if ust_uste >= 3:  # 90 ms boyunca eşiğin üstü: konuşma başladı
                        konusuyor = True
                        kayit = list(on_kayit)
                        konusma_basi = time.monotonic()
                    else:
                        # Ortam gürültüsünü yavaşça takip et
                        self._gurultu = 0.98 * self._gurultu + 0.02 * enerji
                        esik = max(self._gurultu * 3, 250)
                        if time.monotonic() - basla > self.bekleme_sn:
                            return None
                    continue
                kayit.append(blok)
                sessiz_sure = sessiz_sure + blok_sn if enerji < esik else 0.0
                if sessiz_sure >= self.sessizlik_sn or time.monotonic() - konusma_basi > self.azami_sn:
                    break
        ham = self._np.concatenate(kayit).tobytes()
        return metne_cevir(ham, self.dil)


async def _sentezle(metin: str, ses_adi: str) -> bytes:
    import edge_tts

    veri = bytearray()
    async for parca in edge_tts.Communicate(metin, ses_adi).stream():
        if parca["type"] == "audio":
            veri += parca["data"]
    return bytes(veri)


def sentezle(metin: str, ses_adi: str) -> bytes:
    """Metni MP3 sese çevirir."""
    return asyncio.run(_sentezle(metin, ses_adi))


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
        self._havuz = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sentez")

    def hazirla(self, metin: str) -> Future:
        return self._havuz.submit(sentezle, metin, self.ses_adi)

    def konus(self, hazir) -> None:
        mp3 = hazir.result(timeout=30) if isinstance(hazir, Future) else sentezle(hazir, self.ses_adi)
        if not mp3:
            return
        veri, ornekleme = self._sf.read(io.BytesIO(mp3), dtype="float32")
        self._sd.play(veri, ornekleme)
        self._sd.wait()

    def durdur(self) -> None:
        self._sd.stop()

    def kapat(self) -> None:
        self._havuz.shutdown(wait=False, cancel_futures=True)
