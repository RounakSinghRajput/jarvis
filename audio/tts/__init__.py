from audio.tts.base import TTSProvider
from config.settings import settings


def get_tts_provider() -> TTSProvider:
    if settings.tts_provider == "edge":
        from audio.tts.edge_tts_provider import EdgeTTS

        return EdgeTTS(settings.tts_voice, settings.tts_rate or "+0%")
    if settings.tts_provider == "macos_say":
        from audio.tts.macos_say import MacOSSayTTS

        return MacOSSayTTS(settings.tts_voice, int(settings.tts_rate or 190))
    raise ValueError(f"Unknown TTS provider: {settings.tts_provider}")