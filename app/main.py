import logging
import signal
import sys
import threading

from tools import build_registry
from pynput import keyboard
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication

from agent.providers import get_llm_provider
from app.assistant import Assistant
from audio.recorder import MicRecorder
from audio.stt import get_stt_provider
from audio.tts import get_tts_provider
from config.settings import settings
from ui.window import JarvisWindow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jarvis")

SYSTEM_PROMPT = (
    "You are JARVIS, a helpful personal assistant running on the user's Mac. "
    "Always reply in clear, simple English, even if the user's text looks like another language. "
    "Keep answers to one or two short sentences, since they will be spoken aloud. "
    "Do not use markdown, bullet points, or emojis. "
    "You have tools that control the Mac. Use a tool whenever the user asks for an action. "
    "Never say you did something unless the tool result says it worked. "
    "If a tool fails or is not allowed, say so plainly."
)


class Bridge(QObject):
    """Qt signals let the assistant thread talk to the UI thread safely."""

    state_changed = Signal(str)
    text_event = Signal(str, str)
    quit_requested = Signal()


def console_input(assistant: Assistant) -> None:
    """Typed fallback. Empty Enter works like the hotkey."""
    while True:
        try:
            line = input().strip()
        except EOFError:
            break
        if line.lower() in {"quit", "exit"}:
            assistant.shutdown()
            break
        if line:
            assistant.submit_text(line)
        else:
            assistant.on_hotkey()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # the orb hides itself; the app keeps running

    assistant = Assistant(
        llm=get_llm_provider(build_registry()),
        tts=get_tts_provider(),
        stt=get_stt_provider(),
        recorder=MicRecorder(
            silence_threshold=settings.mic_threshold,
            silence_seconds=settings.mic_silence_seconds,
        ),
        system_prompt=SYSTEM_PROMPT,
    )

    # --- connect assistant <-> window ---
    window = JarvisWindow()
    bridge = Bridge()

    def on_state(state) -> None:
        logger.info("UI <- state %s", state.value)
        bridge.state_changed.emit(state.value)

    def on_event(kind: str, text: str) -> None:
        bridge.text_event.emit(kind, text)

    assistant.add_state_listener(on_state)
    assistant.add_event_listener(on_event)

    # QueuedConnection forces window updates to run on the main (UI) thread.
    queued = Qt.ConnectionType.QueuedConnection
    bridge.state_changed.connect(window.on_state, queued)
    bridge.text_event.connect(window.on_text, queued)
    bridge.quit_requested.connect(app.quit, queued)
    window.stop_clicked.connect(assistant.emergency_stop)

    # Startup self-test: the orb flashes for about 2 seconds when the app starts.
    # If you never see it, the problem is the window/display, not the assistant.
    # (Delete these two lines once everything works.)
    QTimer.singleShot(300, lambda: window.on_state("listening"))
    QTimer.singleShot(2500, lambda: window.on_state("idle"))

    # --- hotkey and typed input ---
    hotkey = keyboard.GlobalHotKeys({settings.hotkey: assistant.on_hotkey})
    hotkey.start()
    threading.Thread(target=console_input, args=(assistant,), daemon=True).start()

    # --- Ctrl+C: Qt blocks Python, so a timer gives Python a chance to see it ---
    signal.signal(signal.SIGINT, lambda *_: assistant.shutdown())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(250)

    # --- the assistant loop runs in the background; Qt owns the main thread ---
    def run_assistant() -> None:
        try:
            assistant.run()
        finally:
            bridge.quit_requested.emit()

    threading.Thread(target=run_assistant, daemon=True).start()

    logger.info("Using LLM model: %s", settings.llm_model)
    print(
        f"\nJARVIS ready.\n"
        f"  Hotkey {settings.hotkey}\n"
        f"    - when idle      : start a conversation (keeps listening)\n"
        f"    - while listening: end the conversation\n"
        f"    - while speaking : cancel the current reply\n"
        f"  Say 'ok bye'               -> end the conversation\n"
        f"  Click the orb              -> stop everything\n"
        f"  Enter on an empty line     -> same as the hotkey\n"
        f"  Type a message + Enter     -> text input (single turn)\n"
        f"  'quit' + Enter             -> exit\n"
    )
    try:
        app.exec()
    finally:
        assistant.shutdown()
        hotkey.stop()


if __name__ == "__main__":
    main()