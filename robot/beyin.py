"""Robotun 'beyni': konuşmayı yönetir, hafızayı kullanır, Claude ile yanıt üretir.

Gecikmeyi azaltmak için:
  * Yanıt akış (streaming) olarak alınır ve her cümle tamamlanır tamamlanmaz
    seslendirmeye gönderilir (bkz. robot.metin.CumleBolucu).
  * Sistem istemi sabittir, konuşma geçmişi istem önbelleğine alınır.
  * Varsayılan düşünme derinliği (effort) "low" seviyesindedir.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Protocol

import anthropic

from robot.config import BeyinAyar, HafizaAyar
from robot.istemler import OZET_ISTEMI, hafiza_baglami, sistem_istemi
from robot.memory import araclar
from robot.memory.store import Hafiza
from robot.metin import CumleBolucu

log = logging.getLogger(__name__)

# Sunucu tarafı yedek model (refusal fallback) desteği olan modeller
_YEDEKLI_MODELLER = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
_YEDEK_BETA = "server-side-fallback-2026-07-01"

BAGLANTI_HATASI = "Şu anda düşünme merkezime bağlanamıyorum. İnternet bağlantısını kontrol edip tekrar dener misin?"
REDDEDILDI = "Kusura bakma, bu konuda yardımcı olamıyorum. Başka bir şey konuşalım mı?"
AZAMI_TUR = 40  # Bu kadar turdan sonra konuşma özetlenip yeni konuşmaya geçilir


class Akis(Protocol):
    def metin(self) -> Iterator[str]: ...
    def son_mesaj(self): ...


class DilModeli(Protocol):
    def akis(self, *, system: str, messages: list, tools: list): ...  # context manager -> Akis
    def ozetle(self, dokum: str) -> str: ...


ISITMA_ARALIGI_SN = 240  # Önbellek 5 dk yaşar; boştayken bundan sık ısıtılır


class _ClaudeAkis:
    def __init__(self, stream, baslangic: float):
        self._stream = stream
        self._baslangic = baslangic

    def metin(self) -> Iterator[str]:
        ilk = True
        for olay in self._stream:
            if olay.type == "text":
                if ilk:
                    ilk = False
                    log.info("Modelden ilk kelime: %.0f ms", (time.perf_counter() - self._baslangic) * 1000)
                yield olay.text

    def son_mesaj(self):
        return self._stream.get_final_message()


class ClaudeModel:
    """Anthropic Claude API ile konuşan dil modeli bağdaştırıcısı."""

    def __init__(self, ayar: BeyinAyar, istemci: anthropic.Anthropic | None = None):
        self.ayar = ayar
        # Ses etkileşiminde uzun bekleme istemeyiz: makul zaman aşımı ve tekrar deneme
        self.istemci = istemci or anthropic.Anthropic(timeout=60.0, max_retries=2)
        self._son_istek = float("-inf")  # İlk açılışta hemen ısıt

    def _ortak(self) -> dict:
        p: dict = {"model": self.ayar.model, "output_config": {"effort": self.ayar.effort}}
        if self.ayar.yedek_model and self.ayar.model in _YEDEKLI_MODELLER:
            p["betas"] = [_YEDEK_BETA]
            p["fallbacks"] = "default"
        return p

    def _api(self, p: dict):
        return self.istemci.beta.messages if "betas" in p else self.istemci.messages

    @staticmethod
    def _sistem(system: str) -> list:
        # Araçlar + sistem istemi sabit önek: açık önbellek noktası (ısıtma ile paylaşılır)
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    @contextmanager
    def akis(self, *, system: str, messages: list, tools: list):
        p = self._ortak()
        self._son_istek = time.monotonic()
        baslangic = time.perf_counter()
        with self._api(p).stream(
            **p,
            max_tokens=self.ayar.max_tokens,
            system=self._sistem(system),
            messages=messages,
            tools=tools,
            cache_control={"type": "ephemeral"},  # Geçmişi de önbelleğe al
        ) as stream:
            yield _ClaudeAkis(stream, baslangic)

    def isit(self, *, system: str, tools: list) -> None:
        """Bağlantıyı açar ve sabit öneki önbelleğe yazar (max_tokens=0: yanıt üretilmez).

        Böylece ilk soruda bağlantı kurma ve önbellek yazma beklemesi yaşanmaz.
        """
        p = self._ortak()
        self._son_istek = time.monotonic()
        baslangic = time.perf_counter()
        self._api(p).create(
            **p,
            max_tokens=0,
            system=self._sistem(system),
            tools=tools,
            messages=[{"role": "user", "content": "ısınma"}],
        )
        log.info("Isıtma tamam: %.0f ms", (time.perf_counter() - baslangic) * 1000)

    def bosta_sn(self) -> float:
        return time.monotonic() - self._son_istek

    def ozetle(self, dokum: str) -> str:
        p = self._ortak()
        p["output_config"] = {"effort": "low"}
        with self._api(p).stream(
            **p,
            max_tokens=4000,
            system=OZET_ISTEMI,
            messages=[{"role": "user", "content": dokum}],
        ) as stream:
            mesaj = stream.get_final_message()
        if mesaj.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in mesaj.content if b.type == "text").strip()


class _Reddedildi(Exception):
    pass


class Beyin:
    def __init__(
        self,
        model: DilModeli,
        hafiza: Hafiza,
        hafiza_ayar: HafizaAyar,
        robot_adi: str = "Robi",
    ):
        self.model = model
        self.hafiza = hafiza
        self.ayar = hafiza_ayar
        self.sistem = sistem_istemi(robot_adi)
        self.mesajlar: list[dict] = []
        self.konusma_id: int | None = None
        self._dokum: list[tuple[str, str]] = []
        self._gosterilen: set[int] = set()
        self._aktif = False

    # ------------------------------------------------------------------ ısıtma

    def isitmayi_baslat(self) -> None:
        """Arka planda bağlantıyı ve önbelleği sıcak tutar (model destekliyorsa)."""
        if not hasattr(self.model, "isit"):
            return
        threading.Thread(target=self._isitma_dongusu, daemon=True, name="isitma").start()

    def _isitma_dongusu(self) -> None:
        while True:
            if self.model.bosta_sn() >= ISITMA_ARALIGI_SN:
                try:
                    self.model.isit(system=self.sistem, tools=araclar.ARACLAR)
                except Exception as e:  # Isıtma hatası robotu durdurmamalı
                    log.warning("Isıtma isteği başarısız: %s", e)
            time.sleep(15)

    # ----------------------------------------------------------- konuşma yaşamı

    @property
    def konusma_aktif(self) -> bool:
        return self._aktif

    def konusma_baslat(self) -> None:
        self.mesajlar = []
        self._dokum = []
        self._gosterilen = set()
        self.konusma_id = self.hafiza.konusma_baslat() if self.ayar.konusmalari_kaydet else None
        self._aktif = True

    def konusma_bitir(self) -> None:
        """Konuşmayı kapatır; ayar açıksa özetini çıkarıp hafızaya yazar."""
        if not self._aktif:
            return
        self._aktif = False
        if self.konusma_id is None:
            return
        ozet = None
        if self.ayar.ozet_cikar and len(self._dokum) >= 2:
            dokum = "\n".join(f"{'Kullanıcı' if r == 'kullanici' else 'Robot'}: {m}" for r, m in self._dokum)
            try:
                ozet = self.model.ozetle(dokum) or None
            except anthropic.APIError as e:
                log.warning("Konuşma özeti çıkarılamadı: %s", e)
        self.hafiza.konusma_bitir(self.konusma_id, ozet)

    # ---------------------------------------------------------------- yanıt

    def yanitla(self, metin: str) -> Iterator[str]:
        """Kullanıcının sözüne yanıt verir; seslendirilecek cümleleri sırayla üretir."""
        metin = metin.strip()
        if not metin:
            return
        if self._aktif and len(self._dokum) >= AZAMI_TUR * 2:
            self.konusma_bitir()
        if not self._aktif:
            self.konusma_baslat()

        baslangic = len(self.mesajlar)
        self.mesajlar.append({"role": "user", "content": self._kullanici_icerigi(metin)})
        soylenen: list[str] = []
        try:
            for cumle in self._dongu():
                soylenen.append(cumle)
                yield cumle
        except _Reddedildi:
            del self.mesajlar[baslangic:]
            yield REDDEDILDI
            return
        except anthropic.APIError as e:
            log.error("Dil modeli hatası: %s", e)
            # Bu tur yarım kaldı: geçmişi tur öncesine geri al (sondan kesmek önbelleği bozmaz)
            del self.mesajlar[baslangic:]
            yield BAGLANTI_HATASI
            return

        yanit = " ".join(soylenen)
        self._dokum += [("kullanici", metin), ("robot", yanit)]
        if self.konusma_id is not None:
            self.hafiza.mesaj_ekle(self.konusma_id, "kullanici", metin)
            self.hafiza.mesaj_ekle(self.konusma_id, "robot", yanit)

    def _kullanici_icerigi(self, metin: str) -> str:
        ilk_tur = not self.mesajlar
        kisisel, ozetler = [], []
        if ilk_tur:
            kisisel = self.hafiza.bilgileri_listele("kisisel", 30) + self.hafiza.bilgileri_listele("tercih", 30)
            ozetler = self.hafiza.son_ozetler(self.ayar.ozet_sayisi, haric=self.konusma_id)
        gosterilen = self._gosterilen | {b.id for b in kisisel}
        ilgili = [
            b
            for b in self.hafiza.bilgi_ara(metin, limit=self.ayar.ilgili_bilgi_sayisi)
            if b.id not in gosterilen
        ]
        self._gosterilen = gosterilen | {b.id for b in ilgili}
        baglam = hafiza_baglami(ilk_tur=ilk_tur, kisisel=kisisel, ilgili=ilgili, ozetler=ozetler)
        return f"{baglam}\n\n{metin}" if baglam else metin

    def _dongu(self) -> Iterator[str]:
        json_hatasi = 0
        while True:
            bolucu = CumleBolucu()
            try:
                with self.model.akis(system=self.sistem, messages=self.mesajlar, tools=araclar.ARACLAR) as akis:
                    for parca in akis.metin():
                        yield from bolucu.ekle(parca)
                    mesaj = akis.son_mesaj()
            except ValueError:
                # Araç girdisi hiç ayrıştırılamayacak bir JSON olarak geldi; turu yeniden iste.
                json_hatasi += 1
                if json_hatasi > 2:
                    raise _Reddedildi from None
                continue
            json_hatasi = 0
            yield from bolucu.bitir()

            if mesaj.stop_reason == "refusal":
                raise _Reddedildi
            self.mesajlar.append({"role": "assistant", "content": mesaj.content})
            if mesaj.stop_reason == "pause_turn":
                continue

            arac_cagrilari = [b for b in mesaj.content if b.type == "tool_use"]
            if not arac_cagrilari:
                return
            sonuclar = [self._araci_calistir(b, kesik=mesaj.stop_reason == "max_tokens") for b in arac_cagrilari]
            # Tüm araç sonuçları tek bir kullanıcı mesajında döner
            self.mesajlar.append({"role": "user", "content": sonuclar})

    def _araci_calistir(self, blok, kesik: bool) -> dict:
        sonuc = {"type": "tool_result", "tool_use_id": blok.id}
        if kesik:
            return {**sonuc, "is_error": True, "content": "Girdi yarıda kesildi; daha kısa tekrar dene."}
        try:
            girdi = araclar.dogrula(blok.name, blok.input)
            cikti = araclar.calistir(self.hafiza, blok.name, girdi)
            log.info("Araç %s %s -> %s", blok.name, girdi, cikti)
            return {**sonuc, "content": cikti}
        except (araclar.GecersizGirdi, ValueError) as e:
            log.warning("Geçersiz araç çağrısı %s: %s", blok.name, e)
            return {**sonuc, "is_error": True, "content": f"Geçersiz girdi: {e}"}
