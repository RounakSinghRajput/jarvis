import asyncio
import logging
import os
import queue
import subprocess
import tempfile
import threading

import edge_tts

from audio.tts.base import TTSProvider

logger = logging.getLogger("jarvis.tts")


class EdgeTTS(TTSProvider):
    """Edge neural voice with a pipeline: the next sentence is synthesized
    while the current one is still playing, so there are no gaps."""

    def __init__(self, voice: str = "hi-IN-SwaraNeural", rate: str = "+0%") -> None:
        self._voice = voice
        self._rate = rate
        self._text_q: queue.Queue[tuple[int, str]] = queue.Queue()
        self._audio_q: queue.Queue[tuple[int, str]] = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._generation = 0  # bumped by stop() so stale items get dropped

        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    # ---- public API -------------------------------------------------
    def enqueue(self, text: str) -> None:
        clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
        if clean:
            self._text_q.put((self._generation, clean))

    def wait(self) -> None:
        self._text_q.join()   # everything has been synthesized...
        self._audio_q.join()  # ...and everything has been played

    def speak(self, text: str) -> None:
        self.enqueue(text)
        self.wait()

    def stop(self) -> None:
        self._generation += 1
        self._drain(self._text_q)
        for _gen, path in self._drain(self._audio_q):
            self._remove(path)
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
        logger.info("Speech stopped")

    # ---- workers ----------------------------------------------------
    def _synth_loop(self) -> None:
        while True:
            gen, text = self._text_q.get()
            try:
                if gen != self._generation:
                    continue
                path = self._synthesize(text)
                if path and gen == self._generation:
                    self._audio_q.put((gen, path))
                elif path:
                    self._remove(path)
            except Exception as exc:
                logger.error("Edge TTS failed: %s", exc)
            finally:
                self._text_q.task_done()

    def _play_loop(self) -> None:
        while True:
            gen, path = self._audio_q.get()
            try:
                if gen == self._generation:
                    process = subprocess.Popen(["afplay", path])  # built-in macOS player
                    with self._lock:
                        self._process = process
                    process.wait()
            except Exception as exc:
                logger.error("Playback failed: %s", exc)
            finally:
                with self._lock:
                    self._process = None
                self._remove(path)
                self._audio_q.task_done()

    # ---- helpers ----------------------------------------------------
    def _synthesize(self, text: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        asyncio.run(edge_tts.Communicate(text, self._voice, rate=self._rate).save(path))
        return path

    @staticmethod
    def _drain(q: "queue.Queue") -> list:
        items = []
        while True:
            try:
                items.append(q.get_nowait())
                q.task_done()
            except queue.Empty:
                return items

    @staticmethod
    def _remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass