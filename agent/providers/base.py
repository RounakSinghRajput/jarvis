from abc import ABC, abstractmethod
from collections.abc import Iterator

class LLMProvider(ABC):
    """Every LLM backend must implement this."""

    @abstractmethod
    def generate(self, messages: list[dict[str, str]], system: str = "") -> str:
        """Take the conversation so far and return the assistant's reply."""

    def stream(self, messages: list[dict[str, str]], system: str = "") -> Iterator[str]:
        """Yield the reply in pieces. Default: one piece (no real streaming)."""
        yield self.generate(messages, system)