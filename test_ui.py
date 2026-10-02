import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.window import JarvisWindow

app = QApplication(sys.argv)
window = JarvisWindow()
window.stop_clicked.connect(app.quit)  # in this demo, Stop just closes it

demo = [
    ("listening", None, None),
    ("transcribing", None, None),
    ("thinking", "What is quantum entanglement?", ""),
    ("speaking", None, "Two particles can stay linked, so measuring one tells you about the other."),
    ("idle", None, None),
    ("idle", None, None),
]
step_number = 0


def step() -> None:
    global step_number
    state, user, reply = demo[step_number % len(demo)]
    if user is not None:
        window.on_text("user", user)
    if reply is not None:
        window.on_text("reply", reply)
    window.on_state(state)
    step_number += 1


timer = QTimer()
timer.timeout.connect(step)
timer.start(2000)
step()
sys.exit(app.exec())