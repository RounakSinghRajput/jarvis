import logging
import subprocess

from audio.tts.base import TTSProvider

logger = logging.getLogger("jarvis.tts")


class MacOSSayTTS(TTSProvider):
    def __init__(self, voice: str = "", rate: int = 190) -> None:
        self._voice = voice
        self._rate = rate
        self._process: subprocess.Popen | None = None

    def speak(self, text: str) -> None:
        # Remove markdown symbols so they aren't read aloud.
        clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
        if not clean:
            return

        self.stop()
        command = ["say", "-r", str(self._rate)]
        if self._voice:
            command += ["-v", self._voice]

        try:
            # Text goes in through stdin, so odd characters can't break the command.
            self._process = subprocess.Popen(command, stdin=subprocess.PIPE)
            self._process.communicate(clean.encode("utf-8"))
        except FileNotFoundError:
            logger.error("The 'say' command was not found (this only works on macOS)")
        except Exception as exc:
            logger.error("Speech failed: %s", exc)
        finally:
            self._process = None

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            logger.info("Speech stopped")