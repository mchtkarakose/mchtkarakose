"""Ana döngü: dinle -> anla/düşün -> konuş."""

from __future__ import annotations

import logging
import re
import time

from robot.beyin import Beyin
from robot.govde import Durum, Govde
from robot.memory.store import normalize
from robot.speech import Dinleyici, Konusmaci, SeslendirmeKuyrugu

log = logging.getLogger(__name__)

CIKIS_IFADELERI = {"cikis", "kapan", "kendini kapat", "hosca kal", "gorusuruz", "q"}


def cikis_mi(metin: str) -> bool:
    sade = re.sub(r"[^\w\s]", "", normalize(metin)).strip()
    return sade in CIKIS_IFADELERI


class Robot:
    def __init__(
        self,
        beyin: Beyin,
        dinleyici: Dinleyici,
        konusmaci: Konusmaci,
        govde: Govde | None = None,
        bosta_kalma_sn: float = 300,
        gecikme_goster: bool = False,
        yaziya_dok: bool = False,
    ):
        self.beyin = beyin
        self.dinleyici = dinleyici
        self.konusmaci = konusmaci
        self.govde = govde or Govde()
        self.bosta_kalma_sn = bosta_kalma_sn
        self.gecikme_goster = gecikme_goster
        self.yaziya_dok = yaziya_dok  # Sesli modda duyulanı ve söyleneni ekrana da yaz
        self.gecikmeler_ms: list[float] = []

    def calistir(self) -> None:
        kuyruk = SeslendirmeKuyrugu(self.konusmaci, ilk_ses=lambda: self.govde.durum_degistir(Durum.KONUSUYOR))
        son_etkilesim = time.monotonic()
        self.beyin.isitmayi_baslat()
        try:
            while True:
                self.govde.durum_degistir(Durum.DINLIYOR)
                if self.yaziya_dok:
                    print("[dinliyorum...]", flush=True)
                try:
                    metin = self.dinleyici.dinle()
                except EOFError:
                    break
                except ConnectionError as e:
                    log.error("Dinleme hatası: %s", e)
                    self.govde.durum_degistir(Durum.HATA)
                    time.sleep(2)
                    continue

                bosta = time.monotonic() - son_etkilesim > self.bosta_kalma_sn
                if bosta and self.beyin.konusma_aktif:
                    log.info("Uzun sessizlik: konuşma kapatılıyor ve özetleniyor")
                    self.beyin.konusma_bitir()
                if not metin or not metin.strip():
                    continue
                if cikis_mi(metin):
                    kuyruk.yeni_tur()
                    kuyruk.ekle("Görüşmek üzere!")
                    kuyruk.bekle()
                    break

                self._yanitla(metin, kuyruk)
                son_etkilesim = time.monotonic()
        finally:
            self.govde.durum_degistir(Durum.BEKLIYOR)
            self.beyin.konusma_bitir()
            kuyruk.kapat()
            self.dinleyici.kapat()
            self.konusmaci.kapat()
            self.govde.kapat()

    def _yanitla(self, metin: str, kuyruk: SeslendirmeKuyrugu) -> None:
        self.govde.durum_degistir(Durum.DUSUNUYOR)
        baslangic = time.perf_counter()
        kuyruk.yeni_tur()
        if self.yaziya_dok:
            print(f"Sen: {metin}", flush=True)
        soylenen = []
        for cumle in self.beyin.yanitla(metin):
            kuyruk.ekle(cumle)
            soylenen.append(cumle)
        if self.yaziya_dok:
            print(f"Robot: {' '.join(soylenen)}", flush=True)
        kuyruk.bekle()
        if kuyruk.ilk_ses_zamani is not None:
            ms = (kuyruk.ilk_ses_zamani - baslangic) * 1000
            self.gecikmeler_ms.append(ms)
            log.info("Yanıt gecikmesi (konuşma bitti -> ilk ses): %.0f ms", ms)
            if self.gecikme_goster:
                print(f"  [ilk ses: {ms:.0f} ms]")
