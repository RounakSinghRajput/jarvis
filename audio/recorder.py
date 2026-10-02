import logging
import threading

import numpy as np
import sounddevice as sd

logger = logging.getLogger("jarvis.audio")

SAMPLE_RATE = 16000  # Whisper expects 16 kHz mono audio
BLOCK_SECONDS = 0.1


class MicRecorder:
    """Records from the mic until you stop speaking, or until stop_event is set."""

    def __init__(
        self,
        silence_threshold: float = 0.01,
        silence_seconds: float = 1.0,
        max_seconds: float = 30.0,
        wait_seconds: float = 6.0,
    ) -> None:
        self._threshold = silence_threshold
        self._silence_seconds = silence_seconds
        self._max_seconds = max_seconds
        self._wait_seconds = wait_seconds

    def record(self, stop_event: threading.Event | None = None) -> np.ndarray:
        """Return recorded audio, or an empty array if nobody spoke."""
        block_size = int(SAMPLE_RATE * BLOCK_SECONDS)
        max_blocks = int(self._max_seconds / BLOCK_SECONDS)
        blocks: list[np.ndarray] = []
        heard_speech = False
        silent_blocks = 0
        waited_blocks = 0
        speech_peak = 0.0

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=block_size
        ) as stream:
            # Measure room noise for 0.5 s (kept, so the first words are not lost).
            ambient, _overflowed = stream.read(int(SAMPLE_RATE * 0.5))
            ambient = ambient[:, 0]
            blocks.append(ambient)
            noise = float(np.sqrt(np.mean(ambient**2)))
            start_level = max(self._threshold, noise * 2.5)
            logger.info("Mic noise %.4f -> start level %.4f", noise, start_level)

            for _ in range(max_blocks):
                if stop_event is not None and stop_event.is_set():
                    logger.info("Recording stopped by user")
                    break

                data, _overflowed = stream.read(block_size)
                block = data[:, 0]
                blocks.append(block)
                level = float(np.sqrt(np.mean(block**2)))

                if not heard_speech:
                    if level > start_level:
                        heard_speech = True
                        speech_peak = level
                    else:
                        waited_blocks += 1
                        if waited_blocks * BLOCK_SECONDS >= self._wait_seconds:
                            logger.info("No speech detected")
                            return np.array([], dtype="float32")
                    continue

                # Silence = well below how loud YOU are.
                speech_peak = max(level, speech_peak * 0.99)
                stay_level = max(noise * 2.0, speech_peak * 0.15)
                if level > stay_level:
                    silent_blocks = 0
                else:
                    silent_blocks += 1
                    if silent_blocks * BLOCK_SECONDS >= self._silence_seconds:
                        logger.info("Silence detected")
                        break

        if not heard_speech:
            return np.array([], dtype="float32")
        return np.concatenate(blocks)