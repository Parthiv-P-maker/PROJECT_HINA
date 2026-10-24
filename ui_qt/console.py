"""Scrollback console: user lines, Hina replies (typewriter reveal) and system lines."""

from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser

from ui_qt import theme


class ConsoleLog(QTextBrowser):
    revealing_changed = Signal(bool)

    CHARS_PER_TICK = 2      # x 60 ticks/s = 120 chars/s
    MAX_BLOCKS = 600

    def __init__(self, accent=None, parent=None, clock=datetime.now):
        super().__init__(parent)
        self.setObjectName("Console")
        self.setOpenLinks(False)
        self.setFrameStyle(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.document().setMaximumBlockCount(self.MAX_BLOCKS)
        self.document().setDocumentMargin(4)
        self.viewport().setAutoFillBackground(False)
        self.accent = QColor(accent or "#00e5ff")
        self.clock = clock
        self._pending = ""         # characters still to reveal
        self._pending_fmt = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reveal_step)
        self.typewriter = True

    def set_accent(self, color):
        self.accent = QColor(color)

    # ---- formats ----------------------------------------------------
    def _fmt(self, color, bold=False):
        f = QTextCharFormat()
        f.setForeground(color)
        f.setFontWeight(700 if bold else 400)
        return f

    def _start_line(self, tag, tag_color, when=None):
        self.finish()
        at_bottom = self._at_bottom()
        cur = QTextCursor(self.document())
        cur.movePosition(QTextCursor.End)
        # hanging indent: wrapped lines line up after the "time  TAG " prefix
        indent = QFontMetricsF(self.document().defaultFont()).horizontalAdvance("00:00:00  HINA  ")
        block = QTextBlockFormat()
        block.setTopMargin(3)
        block.setLeftMargin(indent)
        block.setTextIndent(-indent)
        if self.document().isEmpty():
            cur.setBlockFormat(block)
        else:
            cur.insertBlock(block)
        cur.insertText((when or self.clock()).strftime("%H:%M:%S") + "  ", self._fmt(theme.with_alpha(theme.TEXT_DIM, 170)))
        cur.insertText(f"{tag:<5}", self._fmt(tag_color, bold=True))
        cur.insertText(" ", self._fmt(theme.TEXT))
        if at_bottom:
            self._scroll_bottom()
        return cur

    def _at_bottom(self):
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def _scroll_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---- public API -------------------------------------------------
    def add_user(self, text, when=None, dim=False):
        cur = self._start_line("YOU", theme.TEXT_DIM, when)
        cur.insertText(text, self._fmt(theme.TEXT_DIM if dim else theme.TEXT))
        self._scroll_bottom()

    def add_reply(self, text, typewriter=None, when=None, dim=False):
        """`when`/`dim` are for restored history (shown instantly, greyed)."""
        text = theme.hud_text(text)
        if not text:
            return
        cur = self._start_line("HINA", theme.with_alpha(self.accent, 150) if dim else self.accent, when)
        fmt = self._fmt(theme.TEXT_DIM if dim else theme.TEXT.lighter(108))
        if when is not None or dim:
            typewriter = False
        if typewriter if typewriter is not None else self.typewriter:
            self._pending, self._pending_fmt = text, fmt
            self._timer.start(16)
            self.revealing_changed.emit(True)
        else:
            cur.insertText(text, fmt)
            self._scroll_bottom()

    def add_system(self, text, level="info"):
        text = theme.hud_text(text)
        if not text:
            return
        color = {"warn": theme.WARN, "error": theme.DANGER, "ok": theme.OK}.get(
            level, theme.with_alpha(self.accent, 200))
        cur = self._start_line("SYS", color)
        cur.insertText(text, self._fmt(color if level != "info" else theme.with_alpha(theme.TEXT, 190)))
        self._scroll_bottom()

    def is_revealing(self):
        return bool(self._pending)

    def finish(self):
        """Reveal whatever the typewriter hasn't shown yet."""
        if self._pending:
            self._insert(self._pending)
            self._pending = ""
            self._timer.stop()
            self.revealing_changed.emit(False)

    def last_line(self):
        block = self.document().lastBlock()
        return block.text() + (self._pending or "")

    def plain_text(self):
        return self.toPlainText() + (self._pending or "")

    def _insert(self, chunk):
        at_bottom = self._at_bottom()
        cur = QTextCursor(self.document())
        cur.movePosition(QTextCursor.End)
        cur.insertText(chunk, self._pending_fmt)
        if at_bottom:
            self._scroll_bottom()

    def _reveal_step(self):
        if not self._pending:
            self._timer.stop()
            return
        chunk, self._pending = self._pending[:self.CHARS_PER_TICK], self._pending[self.CHARS_PER_TICK:]
        self._insert(chunk)
        if not self._pending:
            self._timer.stop()
            self.revealing_changed.emit(False)
