from audio.stt.base import STTProvider
from config.settings import settings


def get_stt_provider() -> STTProvider:
    if settings.stt_provider == "whisper":
        from audio.stt.whisper_stt import WhisperSTT

        return WhisperSTT(settings.stt_model, settings.stt_language)
    raise ValueError(f"Unknown STT provider: {settings.stt_provider}")