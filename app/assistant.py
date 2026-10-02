import logging
import queue
import re
import threading
import time
from collections.abc import Callable

from agent.providers.base import LLMProvider
from app.state import State
from audio.recorder import MicRecorder
from audio.stt.base import STTProvider
from audio.tts.base import TTSProvider

logger = logging.getLogger("jarvis")

# A sentence ends at . ! ? followed by whitespace.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
MIN_CHUNK_CHARS = 40  # join very short sentences so speech isn't chopped

# "ok bye", "okay, bye", "ok bye bye", "goodbye" (plus common Devanagari spellings)
GOODBYE = re.compile(
    r"\b(?:ok(?:ay)?[\s,.!-]*bye(?:[\s-]*bye)?|good[\s-]?bye)\b"
    r"|(?:ओके|ओ\s?के|अखे|ओक)[\s,.!-]*(?:बाई|बाय|बाइ)(?:[\s-]*(?:बाई|बाय))?"
    r"|(?:गुड\s?बाय|अलविदा)",
    re.IGNORECASE,
)
MAX_WORDS_FOR_GOODBYE = 6   # "I said goodbye to my friend yesterday" must NOT end the session
MAX_SILENT_LISTENS = 3      # this many empty listens in a row ends the session
PAUSE_BEFORE_LISTEN = 0.4   # avoids hearing the tail of JARVIS's own voice
HOTKEY_DEBOUNCE = 0.6       # seconds; ignores key auto-repeat and double presses

StateListener = Callable[[State], None]
EventListener = Callable[[str, str], None]  # (kind, text): kind is "user" or "reply"


class Assistant:
    _last_hotkey: float = 0.0  # time of the last accepted hotkey press

    def __init__(
        self,
        llm: LLMProvider,
        tts: TTSProvider,
        stt: STTProvider,
        recorder: MicRecorder,
        system_prompt: str,
    ) -> None:
        self._llm = llm
        self._tts = tts
        self._stt = stt
        self._recorder = recorder
        self._system_prompt = system_prompt

        self._history: list[dict[str, str]] = []
        self._state = State.IDLE
        self._listeners: list[StateListener] = []
        self._event_listeners: list[EventListener] = []

        # Work items: "" means "start a voice session", other text is typed
        # input, None means "shut down".
        self._requests: queue.Queue[str | None] = queue.Queue()
        self._stop_listening = threading.Event()  # break out of the current recording
        self._end_session = threading.Event()     # end the voice session
        self._cancel = threading.Event()          # abort the current reply

    # ---- listeners (the UI subscribes to these) ------------------------
    @property
    def state(self) -> State:
        return self._state

    def add_state_listener(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    def add_event_listener(self, listener: EventListener) -> None:
        self._event_listeners.append(listener)

    def _set_state(self, state: State) -> None:
        self._state = state
        logger.info("State -> %s", state.value)
        for listener in self._listeners:
            try:
                listener(state)
            except Exception:
                logger.exception("State listener failed")

    def _emit(self, kind: str, text: str) -> None:
        for listener in self._event_listeners:
            try:
                listener(kind, text)
            except Exception:
                logger.exception("Event listener failed")

    # ---- triggers (called from other threads) --------------------------
    def on_hotkey(self) -> None:
        """One key, three meanings depending on what JARVIS is doing."""
        now = time.monotonic()
        if now - self._last_hotkey < HOTKEY_DEBOUNCE:
            return
        self._last_hotkey = now

        if self._state == State.IDLE:
            self._requests.put("")                  # start a session
        elif self._state == State.LISTENING:
            self._end_session.set()                 # end the session
            self._stop_listening.set()
        elif self._state in (State.THINKING, State.SPEAKING):
            self._cancel.set()                      # cancel this reply only
            self._tts.stop()

    def emergency_stop(self) -> None:
        """Orb click: stop speech, cancel the reply, end the session."""
        self._cancel.set()
        self._end_session.set()
        self._stop_listening.set()
        self._tts.stop()

    def submit_text(self, text: str) -> None:
        self._requests.put(text)

    def shutdown(self) -> None:
        self.emergency_stop()
        self._requests.put(None)

    # ---- main loop ---------------------------------------------------
    def run(self) -> None:
        self._set_state(State.IDLE)
        while True:
            request = self._requests.get()
            if request is None:
                break
            self._cancel.clear()
            self._stop_listening.clear()
            self._end_session.clear()
            try:
                self._handle(request)
            except Exception:
                logger.exception("Request failed")
                self._set_state(State.ERROR)
            finally:
                self._set_state(State.IDLE)

    def _handle(self, request: str) -> None:
        if request:
            self._emit("user", request)
            self._think_and_speak(request)  # typed message: single turn
        else:
            self._run_session()             # hotkey: continuous conversation

    # ---- voice session ------------------------------------------------
    def _run_session(self) -> None:
        print("\n--- Session started. Say 'ok bye' to end it. ---")
        silent_listens = 0

        while not self._end_session.is_set():
            text = self._listen()
            if self._end_session.is_set():
                break

            if not text:
                silent_listens += 1
                print("(didn't hear anything)")
                if silent_listens >= MAX_SILENT_LISTENS:
                    self._say("I'll stop listening now. Press the hotkey when you need me.")
                    break
                continue
            silent_listens = 0

            print(f"You said: {text}")
            self._emit("user", text)
            if self._is_goodbye(text):
                self._say("Goodbye!")
                break

            self._cancel.clear()
            self._think_and_speak(text)
            self._cancel.clear()
            time.sleep(PAUSE_BEFORE_LISTEN)

        print("--- Session ended. Press the hotkey to start again. ---\n")

    @staticmethod
    def _is_goodbye(text: str) -> bool:
        return len(text.split()) <= MAX_WORDS_FOR_GOODBYE and GOODBYE.search(text) is not None

    def _say(self, text: str) -> None:
        print(f"JARVIS: {text}")
        self._emit("reply", text)
        self._set_state(State.SPEAKING)
        self._tts.speak(text)

    # ---- one turn ----------------------------------------------------
    def _listen(self) -> str:
        self._stop_listening.clear()
        self._set_state(State.LISTENING)
        started = time.perf_counter()
        audio = self._recorder.record(stop_event=self._stop_listening)
        recorded = time.perf_counter()
        if self._end_session.is_set() or audio.size == 0:
            return ""

        self._set_state(State.TRANSCRIBING)
        text = self._stt.transcribe(audio)
        logger.info(
            "TIMING record=%.1fs (audio %.1fs) | stt=%.1fs",
            recorded - started, len(audio) / 16000, time.perf_counter() - recorded,
        )
        return text

    def _think_and_speak(self, user_text: str) -> None:
        self._set_state(State.THINKING)
        self._emit("reply", "")
        started = time.perf_counter()
        self._history.append({"role": "user", "content": user_text})

        full_reply = ""
        buffer = ""    # text still arriving from the LLM
        pending = ""   # complete sentences waiting to be sent to TTS
        first_token = True
        first_chunk = True
        print("JARVIS: ", end="", flush=True)

        for piece in self._llm.stream(self._history, system=self._system_prompt):
            if self._cancel.is_set():
                break
            if first_token:
                logger.info("TIMING llm first token=%.1fs", time.perf_counter() - started)
                first_token = False
            print(piece, end="", flush=True)
            full_reply += piece
            buffer += piece
            self._emit("reply", full_reply)

            parts = SENTENCE_END.split(buffer)
            for sentence in parts[:-1]:
                pending += sentence + " "
                if len(pending) >= MIN_CHUNK_CHARS:
                    if first_chunk:
                        self._set_state(State.SPEAKING)
                        logger.info("TIMING first chunk=%.1fs", time.perf_counter() - started)
                        first_chunk = False
                    self._tts.enqueue(pending)
                    pending = ""
            buffer = parts[-1]

        print()
        if self._cancel.is_set():
            self._tts.stop()
            logger.info("Reply cancelled by user")
        else:
            leftover = (pending + buffer).strip()
            if leftover:
                self._set_state(State.SPEAKING)
                self._tts.enqueue(leftover)
            self._tts.wait()

        if full_reply:
            self._history.append({"role": "assistant", "content": full_reply})