"""Fiziksel gövde soyutlaması.

Yazılım bilgisayarda çalışırken durumlar konsola yazılır. Donanıma geçildiğinde
bu sınıftan türeyen bir sınıf; LED, ekran, servo motor gibi parçaları sürer.
"""

from __future__ import annotations

import logging
from enum import Enum

log = logging.getLogger(__name__)


class Durum(str, Enum):
    BEKLIYOR = "bekliyor"
    DINLIYOR = "dinliyor"
    DUSUNUYOR = "düşünüyor"
    KONUSUYOR = "konuşuyor"
    HATA = "hata"


class Govde:
    """Varsayılan (sanal) gövde: durumları yalnızca kayda geçirir."""

    def __init__(self) -> None:
        self.durum = Durum.BEKLIYOR

    def durum_degistir(self, durum: Durum) -> None:
        if durum != self.durum:
            log.debug("Gövde durumu: %s -> %s", self.durum.value, durum.value)
            self.durum = durum

    def kapat(self) -> None:
        pass
