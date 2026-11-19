"""Azure AI Speech ile Türkçe konuşma tanıma (STT) ve doğal ses sentezi (TTS).

Kurulum:  pip install -e ".[azure]"
Anahtar:  AZURE_SPEECH_KEY ve AZURE_SPEECH_REGION ortam değişkenleri
"""

from __future__ import annotations

import logging

from robot.speech.base import Dinleyici, Konusmaci

log = logging.getLogger(__name__)


def _sdk():
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            'Azure ses paketi kurulu değil. Kurmak için: pip install -e ".[azure]"'
        ) from e
    return speechsdk


def _yapilandirma(anahtar: str | None, bolge: str | None):
    if not anahtar or not bolge:
        raise RuntimeError("AZURE_SPEECH_KEY ve AZURE_SPEECH_REGION ortam değişkenlerini ayarlayın.")
    return _sdk().SpeechConfig(subscription=anahtar, region=bolge)


class AzureDinleyici(Dinleyici):
    def __init__(self, ses_ayar, anahtar, bolge):
        sdk = _sdk()
        self._sdk = sdk
        yap = _yapilandirma(anahtar, bolge)
        yap.speech_recognition_language = ses_ayar.dil
        # Kullanıcı sustuktan sonra ne kadar beklenip ifadenin bittiğine karar verileceği.
        # Düşük değer = daha hızlı yanıt, fakat cümle ortasındaki duraksamalarda kesilme riski.
        yap.set_property(sdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, str(ses_ayar.sessizlik_ms))
        # Kimse konuşmazsa dinlemeyi bu süre sonra bırak (boşta kalma takibi için)
        yap.set_property(sdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "15000")
        ses = sdk.audio.AudioConfig(use_default_microphone=True)
        self._tanima = sdk.SpeechRecognizer(speech_config=yap, audio_config=ses)

    def dinle(self) -> str | None:
        sonuc = self._tanima.recognize_once_async().get()
        if sonuc.reason == self._sdk.ResultReason.RecognizedSpeech:
            return sonuc.text
        if sonuc.reason == self._sdk.ResultReason.Canceled:
            ayrinti = sonuc.cancellation_details
            log.error("Ses tanıma iptal edildi: %s %s", ayrinti.reason, ayrinti.error_details)
            if ayrinti.reason == self._sdk.CancellationReason.Error:
                raise ConnectionError(ayrinti.error_details)
        return None  # Konuşma algılanmadı


class AzureKonusmaci(Konusmaci):
    def __init__(self, ses_ayar, anahtar, bolge):
        sdk = _sdk()
        self._sdk = sdk
        yap = _yapilandirma(anahtar, bolge)
        yap.speech_synthesis_voice_name = ses_ayar.ses_adi
        ses = sdk.audio.AudioOutputConfig(use_default_speaker=True)
        self._sentez = sdk.SpeechSynthesizer(speech_config=yap, audio_config=ses)
        # Bağlantıyı önceden aç: ilk cümledeki bağlantı kurma gecikmesini ortadan kaldırır
        try:
            sdk.Connection.from_speech_synthesizer(self._sentez).open(True)
        except Exception:  # pragma: no cover
            log.debug("TTS bağlantısı önceden açılamadı", exc_info=True)

    def konus(self, metin: str) -> None:
        sonuc = self._sentez.speak_text_async(metin).get()
        if sonuc.reason == self._sdk.ResultReason.Canceled:
            ayrinti = sonuc.cancellation_details
            log.error("Seslendirme iptal edildi: %s %s", ayrinti.reason, ayrinti.error_details)

    def durdur(self) -> None:
        self._sentez.stop_speaking_async().get()
