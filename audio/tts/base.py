from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """Every text-to-speech backend must implement this."""

    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak the text aloud. Returns when speech finishes."""

    @abstractmethod
    def stop(self) -> None:
        """Stop speaking immediately (needed later for the emergency stop)."""

    def enqueue(self, text: str) -> None:
        """Queue text to be spoken without blocking. Default: speak right away."""
        self.speak(text)

    def wait(self) -> None:
        """Block until everything queued has been spoken. Default: nothing to wait for."""