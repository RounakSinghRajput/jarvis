from abc import ABC, abstractmethod

import numpy as np


class STTProvider(ABC):
    """Every speech-to-text backend must implement this."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """Take 16 kHz mono float32 audio and return the spoken text."""