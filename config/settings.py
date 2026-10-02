import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.5-flash")
    llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "gemini-2.5-flash-lite")
    llm_thinking_level: str = os.getenv("LLM_THINKING_LEVEL", "minimal")
    tts_provider: str = os.getenv("TTS_PROVIDER", "edge")
    tts_voice: str = os.getenv("TTS_VOICE", "hi-IN-SwaraNeural")
    tts_rate: str = os.getenv("TTS_RATE", "")
    stt_provider: str = os.getenv("STT_PROVIDER", "whisper")
    stt_model: str = os.getenv("STT_MODEL", "small")
    stt_language: str = os.getenv("STT_LANGUAGE", "hi")
    mic_threshold: float = float(os.getenv("MIC_THRESHOLD", "0.01"))
    mic_silence_seconds: float = float(os.getenv("MIC_SILENCE_SECONDS", "1.0"))
    hotkey: str = os.getenv("HOTKEY", "<ctrl>+<shift>+j")



settings = Settings()