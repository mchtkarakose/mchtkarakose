"""Akan (streaming) model çıktısını seslendirilebilir parçalara bölme.

Gecikmeyi azaltmak için model cümleyi bitirir bitirmez o cümle seslendirmeye
gönderilir; ilk parça daha da erken (virgülde) kesilebilir.
"""

from __future__ import annotations

import re

_KISALTMALAR = {"dr", "prof", "doç", "sn", "vb", "vs", "örn", "bkz", "yy", "no", "av", "st"}
_BITIS = ".!?…"
_MARKDOWN = re.compile(r"[*_#`>|]+")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def konusmaya_uygun(metin: str) -> str:
    """Seslendirmede sorun çıkaracak biçimlendirmeyi temizler."""
    metin = _LINK.sub(r"\1", metin)
    metin = _MARKDOWN.sub("", metin)
    metin = re.sub(r"^\s*[-•]\s+", "", metin, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", metin).strip()


class CumleBolucu:
    """Gelen metin parçalarını biriktirip tamamlanan cümleleri döndürür."""

    def __init__(self, ilk_parca_min: int = 30, azami_uzunluk: int = 220):
        self._tampon = ""
        self._ilk = True
        self.ilk_parca_min = ilk_parca_min
        self.azami_uzunluk = azami_uzunluk

    def ekle(self, parca: str) -> list[str]:
        self._tampon += parca
        cikti: list[str] = []
        while True:
            kesim = self._kesim_noktasi()
            if kesim is None:
                break
            cumle = konusmaya_uygun(self._tampon[:kesim])
            self._tampon = self._tampon[kesim:]
            if cumle:
                cikti.append(cumle)
                self._ilk = False
        return cikti

    def bitir(self) -> list[str]:
        kalan = konusmaya_uygun(self._tampon)
        self._tampon = ""
        self._ilk = True
        return [kalan] if kalan else []

    def _kesim_noktasi(self) -> int | None:
        t = self._tampon
        for i, ch in enumerate(t):
            sonraki = t[i + 1] if i + 1 < len(t) else None
            if sonraki is None:
                return None  # Sonrasını görmeden karar veremeyiz
            if ch == "\n" and t[:i].strip():
                return i + 1
            if ch in _BITIS and sonraki.isspace():
                if ch == "." and self._kisaltma_mi(t[:i]):
                    continue
                return i + 1
            if ch in ",;:" and sonraki.isspace():
                if (self._ilk and i >= self.ilk_parca_min) or i >= self.azami_uzunluk:
                    return i + 1
        return None

    @staticmethod
    def _kisaltma_mi(onceki: str) -> bool:
        kelime = re.split(r"\s", onceki)[-1].lower()
        return kelime in _KISALTMALAR or kelime.isdigit() or len(kelime) == 1
