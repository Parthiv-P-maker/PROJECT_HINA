"""HUD side widgets: chamfered frames, clock, ring gauges (psutil) and status rows."""

import math
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ui_qt import theme


def chamfer_path(rect, cut=10.0):
    """Rectangle with the top-left and bottom-right corners cut off."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    return QPolygonF([
        QPointF(x + cut, y), QPointF(x + w, y), QPointF(x + w, y + h - cut),
        QPointF(x + w - cut, y + h), QPointF(x, y + h), QPointF(x, y + cut),
    ])


class HudFrame(QWidget):
    """A translucent panel with a chamfered outline, corner brackets and a caption."""

    def __init__(self, caption="", accent=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.caption = caption
        self.accent = QColor(accent or "#00e5ff")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(12, 22 if caption else 10, 12, 10)
        self.body.setSpacing(4)

    def set_accent(self, color):
        self.accent = QColor(color)
        for child in self.findChildren(QWidget):
            if hasattr(child, "set_accent") and child is not self:
                child.set_accent(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        poly = chamfer_path(r, 10)
        p.setBrush(theme.with_alpha(self.accent, 12))
        p.setPen(QPen(theme.with_alpha(self.accent, 70), 1))
        p.drawPolygon(poly)
        # bright corner brackets
        p.setPen(QPen(theme.with_alpha(self.accent, 230), 1.6))
        L = 14
        p.drawLine(QPointF(r.right() - L, r.top()), QPointF(r.right(), r.top()))
        p.drawLine(QPointF(r.right(), r.top()), QPointF(r.right(), r.top() + L))
        p.drawLine(QPointF(r.left(), r.bottom() - L), QPointF(r.left(), r.bottom()))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.left() + L, r.bottom()))
        if self.caption:
            p.setFont(theme.font("mono", 7.5, spacing=2))
            p.setPen(theme.with_alpha(self.accent, 220))
            p.drawText(QRectF(r.left() + 14, r.top() + 4, r.width() - 20, 14), Qt.AlignLeft | Qt.AlignVCenter,
                       self.caption.upper())
            p.setPen(QPen(theme.with_alpha(self.accent, 60), 1))
            fm = p.fontMetrics()
            x0 = r.left() + 20 + fm.horizontalAdvance(self.caption.upper())
            p.drawLine(QPointF(x0, r.top() + 11), QPointF(r.right() - 22, r.top() + 11))
        p.end()


class ClockWidget(QWidget):
    def __init__(self, accent=None, parent=None, now=datetime.now):
        super().__init__(parent)
        self.accent = QColor(accent or "#00e5ff")
        self.now = now
        self.setMinimumHeight(64)
        timer = QTimer(self)
        timer.timeout.connect(self.update)
        timer.start(500)

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = self.now()
        w = self.width()
        p.setFont(theme.font("display", 22, bold=True, spacing=2))
        p.setPen(theme.TEXT)
        p.drawText(QRectF(0, 0, w, 36), Qt.AlignLeft | Qt.AlignVCenter, now.strftime("%H:%M"))
        fm = p.fontMetrics()
        x = fm.horizontalAdvance(now.strftime("%H:%M")) + 6
        p.setFont(theme.font("mono", 10))
        p.setPen(self.accent)
        p.drawText(QRectF(x, 4, 40, 30), Qt.AlignLeft | Qt.AlignVCenter, now.strftime(":%S"))
        p.setFont(theme.font("mono", 8, spacing=1.5))
        p.setPen(theme.TEXT_DIM)
        p.drawText(QRectF(0, 38, w, 14), Qt.AlignLeft, now.strftime("%A").upper())
        p.drawText(QRectF(0, 52, w, 14), Qt.AlignLeft, now.strftime("%d %b %Y").upper())
        # seconds sweep bar
        frac = (now.second + now.microsecond / 1e6) / 60
        p.setPen(QPen(theme.with_alpha(self.accent, 50), 2))
        p.drawLine(QPointF(0, 34), QPointF(w, 34))
        p.setPen(QPen(self.accent, 2))
        p.drawLine(QPointF(0, 34), QPointF(w * frac, 34))
        p.end()


class RingGauge(QWidget):
    """A small circular gauge: value 0..100 (None = unknown)."""

    def __init__(self, label, accent=None, parent=None):
        super().__init__(parent)
        self.label = label
        self.value = None
        self.shown = 0.0
        self.detail = ""
        self.accent = QColor(accent or "#00e5ff")
        self.setMinimumSize(58, 70)
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._step)
        self._anim.start(33)

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def set_value(self, value, detail=""):
        self.value = None if value is None else max(0.0, min(100.0, float(value)))
        self.detail = detail
        self.update()

    def _step(self):
        target = self.value or 0.0
        if abs(target - self.shown) > 0.05:
            self.shown += (target - self.shown) * 0.2
            self.update()

    def _color(self):
        v = self.value or 0
        if self.label == "BAT":
            return theme.DANGER if v < 15 else theme.WARN if v < 30 else self.accent
        return theme.DANGER if v > 90 else theme.WARN if v > 75 else self.accent

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height() - 14)
        r = QRectF((self.width() - side) / 2 + 4, 4, side - 8, side - 8)
        col = self._color()
        p.setPen(QPen(theme.with_alpha(self.accent, 40), 4, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(r, 225 * 16, -270 * 16)
        if self.value is not None:
            p.setPen(QPen(col, 4, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(r, 225 * 16, int(-270 * 16 * self.shown / 100))
        # tick marks
        p.setPen(QPen(theme.with_alpha(self.accent, 90), 1))
        c = r.center()
        for i in range(11):
            a = math.radians(225 - 27 * i)
            ro, ri = r.width() / 2 + 4, r.width() / 2 + 1
            p.drawLine(QPointF(c.x() + math.cos(a) * ri, c.y() - math.sin(a) * ri),
                       QPointF(c.x() + math.cos(a) * ro, c.y() - math.sin(a) * ro))
        p.setFont(theme.font("mono", 9, bold=True))
        p.setPen(theme.TEXT)
        text = "--" if self.value is None else f"{self.value:.0f}"
        p.drawText(r, Qt.AlignCenter, text)
        p.setFont(theme.font("mono", 7, spacing=1.5))
        p.setPen(theme.with_alpha(col, 230))
        p.drawText(QRectF(0, side - 8, self.width(), 14), Qt.AlignHCenter | Qt.AlignTop,
                   self.label + (f" {self.detail}" if self.detail else ""))
        p.end()


class SystemGauges(QWidget):
    """CPU / RAM / battery from psutil, refreshed every 2s (cheap, non-blocking calls)."""

    def __init__(self, accent=None, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.cpu = RingGauge("CPU", accent)
        self.ram = RingGauge("RAM", accent)
        self.bat = RingGauge("BAT", accent)
        for g in (self.cpu, self.ram, self.bat):
            row.addWidget(g)
        self.telemetry = None  # optional Telemetry fed on each refresh
        try:
            import psutil
            self.psutil = psutil
            psutil.cpu_percent(None)  # prime: the first call always returns 0
        except Exception:
            self.psutil = None
        self.refresh()
        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(1000)

    def set_accent(self, color):
        for g in (self.cpu, self.ram, self.bat):
            g.set_accent(color)

    def refresh(self):
        ps = self.psutil
        if ps is None:
            return
        try:
            self.cpu.set_value(ps.cpu_percent(None))
        except Exception:
            self.cpu.set_value(None)
        try:
            self.ram.set_value(ps.virtual_memory().percent)
        except Exception:
            self.ram.set_value(None)
        if self.telemetry is not None:
            self.telemetry.push(self.cpu.value, self.ram.value)
        try:
            bat = ps.sensors_battery()
            if bat is None:
                self.bat.set_value(None, "AC")
            else:
                self.bat.set_value(bat.percent, "+" if bat.power_plugged else "")
        except Exception:
            self.bat.set_value(None)


class Telemetry(QWidget):
    """Scrolling CPU / RAM history, fed by SystemGauges.refresh."""

    SAMPLES = 60

    def __init__(self, accent=None, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent or "#00e5ff")
        self.cpu = []
        self.ram = []
        self.setMinimumHeight(64)

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def push(self, cpu, ram):
        self.cpu = (self.cpu + [cpu or 0.0])[-self.SAMPLES:]
        self.ram = (self.ram + [ram or 0.0])[-self.SAMPLES:]
        self.update()

    def _line(self, values, w, h):
        """Newest sample at the right edge; history grows leftwards as it fills."""
        step = w / (self.SAMPLES - 1)
        x0 = w - step * (len(values) - 1)
        return QPolygonF([QPointF(x0 + i * step, h - 2 - (h - 4) * v / 100) for i, v in enumerate(values)])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height() - 12
        p.setPen(QPen(theme.with_alpha(self.accent, 30), 1))
        for k in range(1, 4):
            p.drawLine(QPointF(0, h * k / 4), QPointF(w, h * k / 4))
        if len(self.cpu) < 2:
            p.end()
            return
        cpu = self._line(self.cpu, w, h)
        fill = QPolygonF(cpu)
        fill.append(QPointF(w, h))
        fill.append(QPointF(cpu[0].x(), h))
        p.setPen(Qt.NoPen)
        p.setBrush(theme.with_alpha(self.accent, 40))
        p.drawPolygon(fill)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self.accent, 1.4))
        p.drawPolyline(cpu)
        p.setPen(QPen(theme.with_alpha(theme.TEXT, 120), 1, Qt.DashLine))
        p.drawPolyline(self._line(self.ram, w, h))
        p.setFont(theme.font("mono", 7, spacing=1.5))
        p.setPen(self.accent)
        p.drawText(QRectF(0, h + 1, w, 11), Qt.AlignLeft, "CPU")
        p.setPen(theme.with_alpha(theme.TEXT, 150))
        p.drawText(QRectF(0, h + 1, w, 11), Qt.AlignRight, "RAM - - 60s")
        p.end()


class StatusRow(QWidget):
    """`LABEL ........ VALUE` with a coloured status pip."""

    def __init__(self, label, accent=None, parent=None):
        super().__init__(parent)
        self.label = label
        self.value = "--"
        self.level = "dim"  # ok / warn / bad / dim / active
        self.accent = QColor(accent or "#00e5ff")
        self.setMinimumHeight(18)

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def set(self, value, level="ok"):
        if (value, level) != (self.value, self.level):
            self.value, self.level = value, level
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = {"ok": theme.OK, "warn": theme.WARN, "bad": theme.DANGER,
               "active": self.accent}.get(self.level, theme.TEXT_DIM)
        h = self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(theme.with_alpha(col, 60))
        p.drawEllipse(QPointF(5, h / 2), 5, 5)
        p.setBrush(col)
        p.drawEllipse(QPointF(5, h / 2), 2.5, 2.5)
        p.setFont(theme.font("mono", 8, spacing=1.2))
        p.setPen(theme.TEXT_DIM)
        p.drawText(QRectF(16, 0, self.width(), h), Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.setPen(col if self.level != "dim" else theme.TEXT_DIM)
        p.drawText(QRectF(0, 0, self.width(), h), Qt.AlignRight | Qt.AlignVCenter, self.value.upper())
        p.end()


class StatusPanel(QWidget):
    def __init__(self, accent=None, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        self.ai = StatusRow("AI LINK", accent)
        self.model = StatusRow("MODEL", accent)
        self.mic = StatusRow("MIC", accent)
        self.voice = StatusRow("VOICE", accent)
        self.mode = StatusRow("MODE", accent)
        self.core = StatusRow("CORE", accent)
        for row in (self.ai, self.model, self.mic, self.voice, self.mode, self.core):
            col.addWidget(row)

    def set_accent(self, color):
        for row in (self.ai, self.model, self.mic, self.voice, self.mode, self.core):
            row.set_accent(color)
