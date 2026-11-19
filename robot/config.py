"""Ayarların yüklenmesi.

Ayarlar `robot.toml` dosyasından okunur; dosya yoksa varsayılanlar kullanılır.
Gizli anahtarlar yalnızca ortam değişkenlerinden okunur.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class RobotAyar:
    ad: str = "Robi"
    kullanici: str = "varsayilan"


@dataclass
class BeyinAyar:
    model: str = "claude-opus-5-5"
    effort: str = "low"
    max_tokens: int = 8000
    yedek_model: bool = True


@dataclass
class HafizaAyar:
    veritabani: str = "data/hafiza.db"
    konusmalari_kaydet: bool = True
    ozet_cikar: bool = True
    ozet_sayisi: int = 3
    ilgili_bilgi_sayisi: int = 5
    bosta_kalma_dk: float = 5


@dataclass
class SesAyar:
    dinleyici: str = "klavye"
    konusmaci: str = "konsol"
    dil: str = "tr-TR"
    ses_adi: str = "tr-TR-EmelNeural"
    sessizlik_ms: int = 600
    mikrofon_hassasiyeti: float = 1.0
    konusma_hizi: str = "+0%"


@dataclass
class Ayarlar:
    robot: RobotAyar = field(default_factory=RobotAyar)
    beyin: BeyinAyar = field(default_factory=BeyinAyar)
    hafiza: HafizaAyar = field(default_factory=HafizaAyar)
    ses: SesAyar = field(default_factory=SesAyar)

    @property
    def azure_anahtar(self) -> str | None:
        return os.environ.get("AZURE_SPEECH_KEY")

    @property
    def azure_bolge(self) -> str | None:
        return os.environ.get("AZURE_SPEECH_REGION")


def _doldur(nesne, veri: dict) -> None:
    gecerli = {f.name: f for f in fields(nesne)}
    for anahtar, deger in veri.items():
        if anahtar not in gecerli:
            raise ValueError(f"Bilinmeyen ayar: {type(nesne).__name__}.{anahtar}")
        setattr(nesne, anahtar, deger)


def yukle(yol: str | Path | None = None) -> Ayarlar:
    ayarlar = Ayarlar()
    yol = Path(yol or os.environ.get("ROBOT_AYAR", "robot.toml"))
    if yol.exists():
        with yol.open("rb") as f:
            veri = tomllib.load(f)
        for bolum, icerik in veri.items():
            if not hasattr(ayarlar, bolum):
                raise ValueError(f"Bilinmeyen ayar bölümü: [{bolum}]")
            _doldur(getattr(ayarlar, bolum), icerik)
    return ayarlar
