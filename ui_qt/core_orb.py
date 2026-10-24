"""
The arc-reactor "core": a QPainter widget that shows what Hina is doing.

    idle       slow breathing, slow counter-rotating rings
    listening  green-shifted, a radial level meter driven by the live mic level
    thinking   amber-shifted, fast spinning segments with comet tails
    speaking   bright, a circular waveform plus ripples expanding from the core

All motion is a function of `self.t` (seconds), advanced by a 60 fps QTimer,
so `advance(dt)` gives deterministic frames for tests and screenshots.
"""

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QBrush, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui_qt import theme

STATES = ("idle", "listening", "thinking", "speaking")
_TINT = {
    "idle": None,
    "listening": QColor(0, 255, 163),
    "thinking": QColor(255, 186, 40),
    "speaking": QColor(150, 240, 255),
}
_ENERGY = {"idle": 0.35, "listening": 0.75, "thinking": 0.85, "speaking": 1.0}
_SPIN = {"idle": 0.12, "listening": 0.25, "thinking": 2.4, "speaking": 0.45}


def _mix(a, b, t):
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class ArcReactor(QWidget):
    FPS = 60

    def __init__(self, accent=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(96, 96)
        self.accent = QColor(accent or "#00e5ff")
        self.state = "idle"
        self.t = 0.0
        self.energy = _ENERGY["idle"]      # smoothed towards the state's target
        self.spin = _SPIN["idle"]
        self.tint = 0.0                    # how far towards the state colour
        self._tint_color = QColor(self.accent)
        self.angle = 0.0                   # integrated rotation (rad), so speed changes stay smooth
        self.level = 0.0                   # smoothed mic level 0..1
        self._target_level = 0.0
        self.levels = [0.0] * 64           # radial meter history
        self.ripples = []                  # [age] of speaking ripples
        self._ripple_clock = 0.0
        self._rng = random.Random(7)
        self._last = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / self.FPS))

    # ---- public API -------------------------------------------------
    def set_state(self, state):
        if state not in STATES:
            raise ValueError(f"unknown core state {state!r}")
        if state != self.state:
            self.state = state
            if state == "speaking":
                self.ripples.append(0.0)
            self.update()

    def set_level(self, level):
        """Live mic RMS mapped to 0..1 (thread-safe enough: a float assignment)."""
        self._target_level = max(0.0, min(1.0, float(level)))

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def advance(self, dt):
        """Step the animation by dt seconds (the timer calls this each frame)."""
        dt = max(0.0, min(dt, 0.1))
        self.t += dt
        k = 1.0 - math.exp(-dt * 6.0)
        self.energy += (_ENERGY[self.state] - self.energy) * k
        self.spin += (_SPIN[self.state] - self.spin) * k
        self.angle += self.spin * dt
        tint = _TINT[self.state]
        if tint is not None:
            self._tint_color = tint
        self.tint += ((1.0 if tint is not None else 0.0) - self.tint) * k

        target = self._target_level if self.state == "listening" else 0.0
        if self.state == "listening" and target <= 0.0:
            target = 0.06 + 0.04 * math.sin(self.t * 5.0)  # idle shimmer with no level source
        self.level += (target - self.level) * (1.0 - math.exp(-dt * 18.0))
        self.levels = self.levels[1:] + [self.level * (0.55 + 0.45 * self._rng.random())]

        if self.state == "speaking":
            self._ripple_clock += dt
            if self._ripple_clock > 0.55:
                self._ripple_clock = 0.0
                self.ripples.append(0.0)
        self.ripples = [age + dt for age in self.ripples if age + dt < 1.6]
        self.update()

    # ---- drawing ----------------------------------------------------
    def _tick(self):
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        if self.isVisible():
            self.advance(dt)

    def color(self):
        return _mix(self.accent, self._tint_color, self.tint * 0.9)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = QPointF(w / 2, h / 2)
        R = min(w, h) / 2 * 0.94
        col = self.color()
        e = self.energy
        breath = 0.5 + 0.5 * math.sin(self.t * (1.3 if self.state == "idle" else 3.2))

        self._halo(p, c, R, col, e, breath)
        self._ripples(p, c, R, col)
        self._outer_ticks(p, c, R, col, e)
        self._arc_segments(p, c, R * 0.86, col, e)
        self._thin_ring(p, c, R * 0.77, col, 70 + 60 * e)
        if self.state == "listening" or self.level > 0.02:
            self._level_meter(p, c, R * 0.70, R * 0.20, col)
        self._coil(p, c, R * 0.60, R * 0.47, col, e, breath)
        if self.state == "speaking":
            self._waveform(p, c, R * 0.41, col)
        self._triangle(p, c, R * 0.38, col, e)
        self._core(p, c, R * 0.30, col, e, breath)
        p.end()

    def _pen(self, color, alpha, width):
        pen = QPen(theme.with_alpha(color, alpha), width)
        pen.setCapStyle(Qt.FlatCap)
        return pen

    def _halo(self, p, c, R, col, e, breath):
        g = QRadialGradient(c, R * 1.05)
        g.setColorAt(0.0, theme.with_alpha(col, 70 + 60 * e * breath))
        g.setColorAt(0.35, theme.with_alpha(col, 26 + 20 * e))
        g.setColorAt(0.75, theme.with_alpha(col, 8))
        g.setColorAt(1.0, theme.with_alpha(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R * 1.05, R * 1.05)

    def _outer_ticks(self, p, c, R, col, e):
        rot = -self.angle * 0.35
        for i in range(120):
            a = rot + i * math.tau / 120
            major = i % 10 == 0
            length = R * (0.07 if major else 0.03)
            alpha = 210 if major else 90 + 50 * e
            p.setPen(self._pen(col, alpha, 1.6 if major else 1.0))
            ca, sa = math.cos(a), math.sin(a)
            p.drawLine(QPointF(c.x() + ca * R, c.y() + sa * R),
                       QPointF(c.x() + ca * (R - length), c.y() + sa * (R - length)))
        # two bright bracket arcs on the outer ring
        p.setPen(self._pen(col, 200, 2.2))
        rect = QRectF(c.x() - R * 1.02, c.y() - R * 1.02, R * 2.04, R * 2.04)
        base = math.degrees(rot) * 16
        for start in (20, 200):
            p.drawArc(rect, int(-base + start * 16), 40 * 16)

    def _arc_segments(self, p, c, r, col, e):
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        deg = math.degrees(self.angle)
        if self.state == "thinking" or self.spin > 1.0:
            # fast spinner: 3 comet arcs with fading tails
            for k in range(3):
                head = deg * 2.2 + k * 120
                for j in range(14):
                    p.setPen(self._pen(col, 230 * (1 - j / 14) ** 1.6, 3.2 - j * 0.12))
                    p.drawArc(rect, int(-(head - j * 4) * 16), int(-4 * 16))
            r2 = r * 0.93
            rect2 = QRectF(c.x() - r2, c.y() - r2, 2 * r2, 2 * r2)
            p.setPen(self._pen(col, 120, 1.4))
            for k in range(12):
                p.drawArc(rect2, int((deg * 3.1 + k * 30) * 16), 14 * 16)
        else:
            spans = [(0, 70), (95, 40), (150, 85), (250, 25), (290, 50)]
            p.setPen(self._pen(col, 120 + 80 * e, 2.4))
            for start, span in spans:
                p.drawArc(rect, int((deg * 1.0 + start) * 16), span * 16)
            r2 = r * 0.93
            rect2 = QRectF(c.x() - r2, c.y() - r2, 2 * r2, 2 * r2)
            p.setPen(self._pen(col, 70 + 40 * e, 1.0))
            for k in range(36):
                if k % 3:
                    p.drawArc(rect2, int((-deg * 0.6 + k * 10) * 16), 6 * 16)

    def _thin_ring(self, p, c, r, col, alpha):
        p.setPen(self._pen(col, alpha, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)

    def _level_meter(self, p, c, r, depth, col):
        n = len(self.levels)
        for i, lv in enumerate(self.levels):
            a = -math.pi / 2 + i * math.tau / n + self.angle * 0.2
            mirror = self.levels[n - 1 - i]
            v = max(lv, mirror) * 1.6
            length = depth * (0.08 + min(1.0, v))
            p.setPen(self._pen(col, 90 + 160 * min(1.0, v), 2.0))
            ca, sa = math.cos(a), math.sin(a)
            p.drawLine(QPointF(c.x() + ca * r, c.y() + sa * r),
                       QPointF(c.x() + ca * (r - length), c.y() + sa * (r - length)))

    def _coil(self, p, c, r_out, r_in, col, e, breath):
        """The arc-reactor coil ring: 10 trapezoid segments with gaps."""
        n = 10
        gap = math.radians(7)
        rot = self.angle * 0.5
        for i in range(n):
            a0 = rot + i * math.tau / n + gap / 2
            a1 = rot + (i + 1) * math.tau / n - gap / 2
            path = QPainterPath()
            steps = 8
            for s in range(steps + 1):
                a = a0 + (a1 - a0) * s / steps
                pt = QPointF(c.x() + math.cos(a) * r_out, c.y() + math.sin(a) * r_out)
                path.moveTo(pt) if s == 0 else path.lineTo(pt)
            for s in range(steps, -1, -1):
                a = a0 + (a1 - a0) * s / steps
                path.lineTo(QPointF(c.x() + math.cos(a) * r_in, c.y() + math.sin(a) * r_in))
            path.closeSubpath()
            phase = 0.5 + 0.5 * math.sin(self.t * 2.0 + i * 0.63)
            fill = 25 + 70 * e * (0.4 + 0.6 * (phase if self.state != "idle" else breath))
            p.setBrush(theme.with_alpha(col, fill))
            p.setPen(self._pen(col, 140 + 80 * e, 1.0))
            p.drawPath(path)

    def _waveform(self, p, c, r, col):
        amp = r * 0.22 * self.energy * min(1.0, self.tint * 1.4 + 0.2)
        path = QPainterPath()
        steps = 160
        for s in range(steps + 1):
            a = s * math.tau / steps
            wobble = (math.sin(a * 6 + self.t * 9) * 0.5 + math.sin(a * 11 - self.t * 13) * 0.3
                      + math.sin(a * 3 + self.t * 5) * 0.2)
            env = 0.6 + 0.4 * math.sin(self.t * 7.0)
            rr = r + amp * wobble * env
            pt = QPointF(c.x() + math.cos(a) * rr, c.y() + math.sin(a) * rr)
            path.moveTo(pt) if s == 0 else path.lineTo(pt)
        p.setBrush(Qt.NoBrush)
        p.setPen(self._pen(col, 70, 5.0))
        p.drawPath(path)
        p.setPen(self._pen(_mix(col, QColor(255, 255, 255), 0.4), 230, 1.4))
        p.drawPath(path)

    def _ripples(self, p, c, R, col):
        p.setBrush(Qt.NoBrush)
        for age in self.ripples:
            k = age / 1.6
            r = R * (0.32 + 0.75 * k)
            p.setPen(self._pen(col, 200 * (1 - k) ** 2, 2.0 * (1 - k) + 0.6))
            p.drawEllipse(c, r, r)

    def _triangle(self, p, c, r, col, e):
        rot = -self.angle * 0.8 - math.pi / 2
        pts = [QPointF(c.x() + math.cos(rot + k * math.tau / 3) * r,
                       c.y() + math.sin(rot + k * math.tau / 3) * r) for k in range(3)]
        p.setBrush(Qt.NoBrush)
        p.setPen(self._pen(col, 90 + 90 * e, 1.4))
        p.drawPolygon(QPolygonF(pts))
        inner = [QPointF(c.x() + math.cos(-rot + math.pi / 3 + k * math.tau / 3) * r * 0.62,
                         c.y() + math.sin(-rot + math.pi / 3 + k * math.tau / 3) * r * 0.62) for k in range(3)]
        p.setPen(self._pen(col, 60 + 60 * e, 1.0))
        p.drawPolygon(QPolygonF(inner))

    def _core(self, p, c, r, col, e, breath):
        pulse = 1.0 + 0.06 * breath + 0.25 * self.level
        g = QRadialGradient(c, r * pulse)
        white = QColor(255, 255, 255)
        g.setColorAt(0.0, theme.with_alpha(white, 255))
        g.setColorAt(0.18, theme.with_alpha(_mix(col, white, 0.65), 245))
        g.setColorAt(0.45, theme.with_alpha(col, 150 + 60 * e))
        g.setColorAt(0.8, theme.with_alpha(col, 40 + 30 * e * breath))
        g.setColorAt(1.0, theme.with_alpha(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r * pulse, r * pulse)
        p.setBrush(Qt.NoBrush)
        p.setPen(self._pen(_mix(col, white, 0.5), 160 + 80 * e, 1.6))
        p.drawEllipse(c, r * 0.52, r * 0.52)
