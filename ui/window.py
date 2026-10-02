import logging
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("jarvis.ui")

# ---- size: change ORB_RADIUS to make the whole thing smaller or bigger -------
ORB_RADIUS = 22                 # the glass ball is 2 x 22 = 44 px wide
SIZE = int(ORB_RADIUS * 5)      # window size; leaves room for the glow and rings
BOTTOM_MARGIN = 24              # gap between the orb and the bottom of the screen

# state -> (primary color, secondary color, motion speed, breathing size)
STATES = {
    "idle": ("#8c96b0", "#566079", 0.012, 0.015),
    "listening": ("#22d3ee", "#3b82f6", 0.035, 0.07),
    "transcribing": ("#fbbf24", "#f97316", 0.070, 0.03),
    "thinking": ("#a78bfa", "#ec4899", 0.080, 0.04),
    "speaking": ("#34d399", "#22d3ee", 0.050, 0.08),
    "error": ("#f87171", "#dc2626", 0.000, 0.00),
}

# state -> which outer effect is shown
EFFECT = {
    "listening": "ripple",
    "speaking": "wave",
    "thinking": "spinner",
    "transcribing": "spinner",
}

WHITE = [255.0, 255.0, 255.0]
BLACK = [0.0, 0.0, 0.0]


def _rgb(hex_color: str) -> list[float]:
    c = QColor(hex_color)
    return [float(c.red()), float(c.green()), float(c.blue())]


def _color(rgb: list[float], alpha: int = 255) -> QColor:
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), max(0, min(255, alpha)))


def _mix(a: list[float], b: list[float], t: float) -> list[float]:
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


class JarvisWindow(QWidget):
    stop_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"
        self._phase = 0.0

        primary, secondary, speed, pulse = STATES["idle"]
        self._c1, self._c2 = _rgb(primary), _rgb(secondary)
        self._t1, self._t2 = list(self._c1), list(self._c2)
        self._speed, self._t_speed = speed, speed
        self._pulse, self._t_pulse = pulse, pulse
        self._fx = {"ripple": 0.0, "wave": 0.0, "spinner": 0.0}
        self._t_fx = dict(self._fx)
        self._opacity = 0.0
        self._t_opacity = 0.0

        # Borderless, transparent, always on top, never takes keyboard focus.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFixedSize(SIZE, SIZE)
        self.setWindowOpacity(0.0)

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)  # about 60 frames per second

    # ---- called from main.py (via Qt signals) ---------------------------
    def on_state(self, state: str) -> None:
        logger.info("Orb received state: %s", state)
        previous = self._state
        self._state = state
        primary, secondary, speed, pulse = STATES.get(state, STATES["idle"])
        self._t1, self._t2 = _rgb(primary), _rgb(secondary)
        self._t_speed, self._t_pulse = speed, pulse

        active = EFFECT.get(state)
        for name in self._t_fx:
            self._t_fx[name] = 1.0 if name == active else 0.0

        if state == "idle":
            if previous != "idle":
                QTimer.singleShot(1200, self._fade_out_if_idle)
        else:
            self._fade_in()

    def on_text(self, kind: str, text: str) -> None:
        """The orb shows no text. Kept so main.py doesn't need to change."""

    # ---- helpers -----------------------------------------------------
    def _fade_in(self) -> None:
        self._t_opacity = 1.0
        if not self.isVisible():
            self._opacity = 0.0
            self.setWindowOpacity(0.0)
            self._place()
            self.show()
            logger.info(
                "Showing orb at %s,%s on screen %s",
                self.x(), self.y(), QGuiApplication.primaryScreen().availableGeometry(),
            )
        self.raise_()

    def _fade_out_if_idle(self) -> None:
        if self._state == "idle":
            self._t_opacity = 0.0

    def _place(self) -> None:
        """Bottom-center of the screen."""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - SIZE // 2,
            screen.bottom() - SIZE - BOTTOM_MARGIN,
        )

    def _tick(self) -> None:
        if not self.isVisible():
            return
        # Ease everything toward its target so changes look smooth, never snappy.
        for i in range(3):
            self._c1[i] += (self._t1[i] - self._c1[i]) * 0.10
            self._c2[i] += (self._t2[i] - self._c2[i]) * 0.10
        self._speed += (self._t_speed - self._speed) * 0.06
        self._pulse += (self._t_pulse - self._pulse) * 0.06
        for name in self._fx:
            self._fx[name] += (self._t_fx[name] - self._fx[name]) * 0.10
        self._phase += self._speed
        self._opacity += (self._t_opacity - self._opacity) * 0.14
        self.setWindowOpacity(self._opacity)

        if self._t_opacity == 0.0 and self._opacity < 0.02:
            self.hide()
            return
        self.update()

    # ---- drawing -----------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        no_pen = Qt.PenStyle.NoPen
        no_brush = Qt.BrushStyle.NoBrush

        c = QPointF(SIZE / 2, SIZE / 2)
        R = float(ORB_RADIUS)

        # pop-in: slightly smaller while fading in or out
        scale = 0.75 + 0.25 * self._opacity
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)

        breathe = 1 + self._pulse * math.sin(self._phase * 2.0)
        r = R * breathe

        # 1) soft halo
        p.setPen(no_pen)
        halo_r = R * 2.3 * breathe
        halo = QRadialGradient(c, halo_r)
        halo.setColorAt(0.30, _color(self._c1, 70))
        halo.setColorAt(1.00, _color(self._c1, 0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(c, halo_r, halo_r)

        # 2) listening: sonar ripples
        w = self._fx["ripple"]
        if w > 0.02:
            p.setBrush(no_brush)
            for k in range(2):
                t = (self._phase * 0.35 + k * 0.5) % 1.0
                ring_r = r + t * R * 1.0
                alpha = int(120 * w * (1 - t) ** 1.5)
                p.setPen(QPen(_color(self._c1, alpha), 1.4))
                p.drawEllipse(c, ring_r, ring_r)

        # 3) speaking: soft wobbling wave ring (like a voice waveform)
        w = self._fx["wave"]
        if w > 0.02:
            p.setBrush(no_brush)
            for layer, (color, width, phase_shift) in enumerate(
                ((self._c2, 1.6, 0.0), (self._c1, 1.0, 1.7))
            ):
                path = QPainterPath()
                n = 96
                base_r = r + R * 0.38
                amp = R * 0.16 * w * (0.6 + 0.4 * math.sin(self._phase * 3.1 + layer))
                for i in range(n + 1):
                    a = 2 * math.pi * i / n
                    wobble = (
                        math.sin(3 * a + self._phase * 2.2 + phase_shift) * 0.6
                        + math.sin(5 * a - self._phase * 3.0 + phase_shift) * 0.4
                    )
                    rr = base_r + amp * wobble
                    pt = QPointF(c.x() + math.cos(a) * rr, c.y() + math.sin(a) * rr)
                    if i == 0:
                        path.moveTo(pt)
                    else:
                        path.lineTo(pt)
                alpha = 200 if layer == 0 else 110
                p.setPen(QPen(_color(color, int(alpha * w)), width))
                p.drawPath(path)

        # 4) thinking / processing: two spinning arcs
        w = self._fx["spinner"]
        if w > 0.02:
            ring = r + R * 0.45
            rect = QRectF(c.x() - ring, c.y() - ring, ring * 2, ring * 2)
            pen = QPen(_color(self._c1, int(210 * w)), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(no_brush)
            for k in range(2):
                start = -int((self._phase * 55 + k * 180) * 16)
                p.drawArc(rect, start, 80 * 16)

        # 5) the glass orb itself (everything inside is clipped to the circle)
        p.save()
        clip = QPainterPath()
        clip.addEllipse(c, r, r)
        p.setClipPath(clip)
        p.setPen(no_pen)

        body = QRadialGradient(QPointF(c.x() - r * 0.35, c.y() - r * 0.40), r * 1.7)
        body.setColorAt(0.00, _color(_mix(self._c1, WHITE, 0.55)))
        body.setColorAt(0.45, _color(self._c1))
        body.setColorAt(1.00, _color(_mix(self._c2, BLACK, 0.35)))
        p.setBrush(QBrush(body))
        p.drawEllipse(c, r, r)

        # aurora blobs drifting inside the glass
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        blob_colors = (self._c1, self._c2, _mix(self._c1, self._c2, 0.5))
        for i, col in enumerate(blob_colors):
            ang = self._phase * (0.9 + 0.35 * i) + i * 2.4
            center = QPointF(
                c.x() + math.cos(ang) * r * 0.45,
                c.y() + math.sin(ang * 1.25) * r * 0.45,
            )
            blob_r = r * 0.85
            blob = QRadialGradient(center, blob_r)
            blob.setColorAt(0.0, _color(col, 95))
            blob.setColorAt(1.0, _color(col, 0))
            p.setBrush(QBrush(blob))
            p.drawEllipse(center, blob_r, blob_r)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # glossy highlight, top-left
        hl_center = QPointF(c.x() - r * 0.38, c.y() - r * 0.45)
        highlight = QRadialGradient(hl_center, r * 0.55)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 150))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(highlight))
        p.drawEllipse(hl_center, r * 0.55, r * 0.40)
        p.restore()

        # 6) thin rim of light that slowly rotates around the orb
        rim = QConicalGradient(c, (-self._phase * 40) % 360)
        rim.setColorAt(0.00, QColor(255, 255, 255, 200))
        rim.setColorAt(0.35, _color(self._c1, 40))
        rim.setColorAt(0.70, _color(self._c2, 160))
        rim.setColorAt(1.00, QColor(255, 255, 255, 200))
        p.setBrush(no_brush)
        p.setPen(QPen(QBrush(rim), 1.5))
        p.drawEllipse(c, r, r)

    # Click the orb to stop everything (delete this method if you don't want it).
    def mousePressEvent(self, _event) -> None:
        self.stop_clicked.emit()