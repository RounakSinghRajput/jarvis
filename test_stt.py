import logging

from audio.recorder import MicRecorder
from audio.stt import get_stt_provider
from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

stt = get_stt_provider()
recorder = MicRecorder(
    silence_threshold=settings.mic_threshold,
    silence_seconds=settings.mic_silence_seconds,
)

while True:
    input("\nEnter dabao, phir bolo (Ctrl+C = exit): ")
    audio = recorder.record()
    print(f"Duration: {len(audio) / 16000:.1f}s")
    print("Text:", stt.transcribe(audio))