"""Bilgisayarda test için klavye girişi ve ekrana yazı çıkışı."""

from __future__ import annotations

import sys

from robot.speech.base import Dinleyici, Konusmaci


class KlavyeDinleyici(Dinleyici):
    def __init__(self, istem: str = "Sen: "):
        self.istem = istem

    def dinle(self) -> str | None:
        try:
            return input(self.istem)
        except KeyboardInterrupt:
            raise EOFError from None


class KonsolKonusmaci(Konusmaci):
    def __init__(self, on_ek: str = "Robot: "):
        self.on_ek = on_ek
        self._satir_basi = True

    def konus(self, metin: str) -> None:
        if self._satir_basi:
            sys.stdout.write(self.on_ek)
            self._satir_basi = False
        else:
            sys.stdout.write(" ")
        sys.stdout.write(metin)
        sys.stdout.flush()

    def tur_sonu(self) -> None:
        if not self._satir_basi:
            sys.stdout.write("\n")
            sys.stdout.flush()
        self._satir_basi = True
