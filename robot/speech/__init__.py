"""Ses giriş/çıkış katmanı.

Dinleyici (Listener): mikrofondan konuşmayı algılayıp metne çevirir.
Konuşmacı (Speaker): metni doğal sesle seslendirir.
Yeni bir sağlayıcı eklemek için base.py'deki arayüzleri uygulamak yeterlidir.
"""

from robot.speech.base import Dinleyici, Konusmaci, SeslendirmeKuyrugu

__all__ = ["Dinleyici", "Konusmaci", "SeslendirmeKuyrugu", "olustur"]


def olustur(ses_ayar, ayarlar):
    """Ayarlara göre dinleyici ve konuşmacı nesnelerini oluşturur."""
    if ses_ayar.dinleyici == "klavye":
        from robot.speech.konsol import KlavyeDinleyici

        dinleyici = KlavyeDinleyici()
    elif ses_ayar.dinleyici == "azure":
        from robot.speech.azure import AzureDinleyici

        dinleyici = AzureDinleyici(ses_ayar, ayarlar.azure_anahtar, ayarlar.azure_bolge)
    else:
        raise ValueError(f"Bilinmeyen dinleyici: {ses_ayar.dinleyici}")

    if ses_ayar.konusmaci == "konsol":
        from robot.speech.konsol import KonsolKonusmaci

        konusmaci = KonsolKonusmaci()
    elif ses_ayar.konusmaci == "azure":
        from robot.speech.azure import AzureKonusmaci

        konusmaci = AzureKonusmaci(ses_ayar, ayarlar.azure_anahtar, ayarlar.azure_bolge)
    else:
        raise ValueError(f"Bilinmeyen konuşmacı: {ses_ayar.konusmaci}")
    return dinleyici, konusmaci
