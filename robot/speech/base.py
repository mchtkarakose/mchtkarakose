from __future__ import annotations

import queue
import threading
import time
from abc import ABC, abstractmethod
from typing import Callable


class Dinleyici(ABC):
    @abstractmethod
    def dinle(self) -> str | None:
        """Bir konuşma (ifade) bitene kadar dinler ve metnini döndürür.

        Sessizlikte zaman aşımına uğrarsa None, kapatılması istenirse EOFError fırlatır.
        """

    def kapat(self) -> None:
        pass


class Konusmaci(ABC):
    @abstractmethod
    def konus(self, metin: str) -> None:
        """Metni seslendirir; seslendirme bitene kadar bekler."""

    def durdur(self) -> None:
        """Devam eden seslendirmeyi keser (söz kesme / barge-in için)."""

    def tur_sonu(self) -> None:
        """Bir yanıtın tüm cümleleri seslendirildiğinde çağrılır."""

    def kapat(self) -> None:
        pass


class SeslendirmeKuyrugu:
    """Cümleleri arka planda sırayla seslendirir.

    Model bir sonraki cümleyi üretirken önceki cümle çalınabilsin diye
    seslendirme ayrı bir iş parçacığında yapılır.
    """

    def __init__(self, konusmaci: Konusmaci, ilk_ses: Callable[[], None] | None = None):
        self.konusmaci = konusmaci
        self._kuyruk: queue.Queue[str | None] = queue.Queue()
        self._ilk_ses = ilk_ses
        self._ilk_bekleniyor = False
        self.ilk_ses_zamani: float | None = None
        self._is = threading.Thread(target=self._calis, daemon=True, name="seslendirme")
        self._is.start()

    def yeni_tur(self) -> None:
        self._ilk_bekleniyor = True
        self.ilk_ses_zamani = None

    def ekle(self, cumle: str) -> None:
        self._kuyruk.put(cumle)

    def bekle(self) -> None:
        """Kuyruktaki her şey seslendirilene kadar bekler."""
        self._kuyruk.join()
        self.konusmaci.tur_sonu()

    def kapat(self) -> None:
        self._kuyruk.put(None)
        self._is.join(timeout=5)

    def _calis(self) -> None:
        while True:
            cumle = self._kuyruk.get()
            try:
                if cumle is None:
                    return
                if self._ilk_bekleniyor:
                    self._ilk_bekleniyor = False
                    self.ilk_ses_zamani = time.perf_counter()
                    if self._ilk_ses:
                        self._ilk_ses()
                self.konusmaci.konus(cumle)
            except Exception:  # Seslendirme hatası robotu durdurmamalı
                import logging

                logging.getLogger(__name__).exception("Seslendirme hatası")
            finally:
                self._kuyruk.task_done()
