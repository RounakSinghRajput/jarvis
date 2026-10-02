import logging

import numpy as np

from audio.stt.base import STTProvider

logger = logging.getLogger("jarvis.stt")


class WhisperSTT(STTProvider):
    def __init__(self, model_size: str = "small", language: str = "hi") -> None:
        from faster_whisper import WhisperModel

        logger.info("Loading Whisper model '%s' (first run downloads it)...", model_size)
        # int8 on CPU is fast and light enough for an M4.
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self._language = language or None  # None = auto-detect
        logger.info("Whisper ready")

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        try:
            segments, _info = self._model.transcribe(
                audio, language=self._language, beam_size=5, vad_filter=True
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            return ""