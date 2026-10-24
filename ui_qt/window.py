"""
HinaWindow: the frameless, translucent, always-on-top HUD.

    title strip   H.I.N.A. mark, status, [YES][NO], compact, settings, hide, quit
    left column   clock / system gauges / status rows        (expanded only)
    centre        the arc-reactor core + state caption
    right         console log with scrollback
    bottom        command input, mic (push-to-talk), send
"""

import random
import re
import threading
import time
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSizePolicy,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from ui_qt import settings as settings_mod
from ui_qt import theme
from ui_qt.bridge import HinaBridge
from ui_qt.console import ConsoleLog
from ui_qt.core_orb import ArcReactor
from ui_qt.hud import ClockWidget, HudFrame, StatusPanel, SystemGauges, Telemetry, chamfer_path
from ui_qt.settings_panel import SettingsPanel
from utils.logger import get_logger

logger = get_logger(__name__)

EXPANDED_SIZE = (1000, 620)
COMPACT_SIZE = (560, 330)
HISTORY_ON_START = 12   # earlier turns shown in the console at startup

STATE_CAPTIONS = {
    "idle": "STANDBY",
    "listening": "LISTENING",
    "thinking": "PROCESSING",
    "speaking": "SPEAKING",
}
VOICE_STATE_TEXT = {
    "waiting": "WAITING FOR AUDIO CHANNEL",
    "listening": "RECEIVING AUDIO",
    "transcribing": "TRANSCRIBING",
}
AMBIENT_LINES = [
    "All systems nominal. Standing by.",
    "Quiet on all channels. I'm here when you need me.",
    "Background diagnostics complete. Nothing to report.",
    "You've been focused for a while. Consider a short break.",
    "Idle cycle. Say the word and I'll get to work.",
]


# Spoken phrases that would shut Hina down. Whisper sometimes "hears" one of these
# from unclear audio, so voice never quits without a yes.
EXIT_PHRASES = {"bye", "bye bye", "goodbye", "good bye", "exit", "quit",
                "bye hina", "goodbye hina", "exit hina", "quit hina"}


def is_exit_phrase(text):
    return re.sub(r"[^a-z ]", "", (text or "").lower()).strip() in EXIT_PHRASES


def greeting(name=None, now=None):
    hour = (now or datetime.now()).hour
    part = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"
    who = f", {name}" if name else ""
    return random.choice([
        f"Good {part}{who}. All systems are online.",
        f"Good {part}{who}. Hina online and at your service.",
        f"Systems online. Good {part}{who}.",
    ])


def make_icon(accent, size=64):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(size / 2, size / 2)
    g = QRadialGradient(c, size / 2)
    g.setColorAt(0, QColor(255, 255, 255))
    g.setColorAt(0.3, accent)
    g.setColorAt(1, theme.with_alpha(accent, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(c, size * 0.3, size * 0.3)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(accent, size / 14))
    p.drawEllipse(c, size * 0.42, size * 0.42)
    p.end()
    return QIcon(pix)


class HinaWindow(QWidget):
    hotkey_toggle = Signal()
    hotkey_talk = Signal()
    ai_status = Signal(bool)
    quit_requested = Signal()

    def __init__(self, settings=None, bridge=None, hotkeys=True, tray=True, speak=None, parent=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else settings_mod.load()
        self.bridge = bridge or HinaBridge(self.settings)
        self.bridge.settings = self.settings
        self._speak = speak
        self.accent = theme.accent(self.settings)
        self.state = "idle"
        self.voice_status = ""
        self.compact = bool(self.settings.get("compact"))
        self._pending_exit = False
        self._reported_missing_model = None
        self.last_activity = time.time()
        self.last_ambient = 0.0
        self._hotkey_handles = []
        self._quitting = False
        self._bg_cache = None

        self.setWindowTitle("Project Hina")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_flags()
        self.setWindowIcon(make_icon(self.accent))

        self._build()
        self._wire()
        self.apply_settings(self.settings, first=True)
        self.set_compact(self.compact, save=False)
        self._restore_position()

        self.tray = self._make_tray() if tray else None
        if hotkeys:
            self.register_hotkeys()

        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self.refresh_state)
        self._state_timer.start(100)
        self._ambient_timer = QTimer(self)
        self._ambient_timer.timeout.connect(self._ambient_tick)
        self._ambient_timer.start(30_000)
        self._ai_timer = QTimer(self)
        self._ai_timer.timeout.connect(self.check_ai)
        self._ai_timer.start(15_000)
        self._save_pos_timer = QTimer(self)
        self._save_pos_timer.setSingleShot(True)
        self._save_pos_timer.timeout.connect(self._save_position)
        QTimer.singleShot(200, self.check_ai)

    # =================================================================
    # construction
    # =================================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 12)
        root.setSpacing(8)
        root.addWidget(self._build_title())

        body = QHBoxLayout()
        body.setSpacing(10)

        # ---- left HUD column ----
        self.left_col = QWidget()
        self.left_col.setFixedWidth(220)
        lc = QVBoxLayout(self.left_col)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(8)
        self.clock_frame = HudFrame("Chronometer", self.accent)
        self.clock = ClockWidget(self.accent)
        self.clock_frame.body.addWidget(self.clock)
        self.sys_frame = HudFrame("System", self.accent)
        self.gauges = SystemGauges(self.accent)
        self.sys_frame.body.addWidget(self.gauges)
        self.status_frame = HudFrame("Status", self.accent)
        self.status = StatusPanel(self.accent)
        self.status_frame.body.addWidget(self.status)
        self.tele_frame = HudFrame("Telemetry", self.accent)
        self.telemetry = Telemetry(self.accent)
        self.gauges.telemetry = self.telemetry
        self.tele_frame.body.addWidget(self.telemetry)
        lc.addWidget(self.clock_frame)
        lc.addWidget(self.sys_frame)
        lc.addWidget(self.status_frame)
        lc.addWidget(self.tele_frame, 1)
        body.addWidget(self.left_col)

        # ---- centre core ----
        self.center_col = QWidget()
        cc = QVBoxLayout(self.center_col)
        cc.setContentsMargins(0, 0, 0, 0)
        cc.setSpacing(2)
        self.core = ArcReactor(self.accent)
        cc.addWidget(self.core, 1)
        self.state_label = QLabel()
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setObjectName("Caption")
        self.sub_label = QLabel()
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setObjectName("Dim")
        cc.addWidget(self.state_label)
        cc.addWidget(self.sub_label)
        body.addWidget(self.center_col, 1)

        # ---- console ----
        self.console_frame = HudFrame("Console", self.accent)
        self.console = ConsoleLog(self.accent)
        self.console_frame.body.addWidget(self.console)
        self.console_frame.setMinimumWidth(300)
        body.addWidget(self.console_frame, 1)
        root.addLayout(body, 1)

        # ---- input bar ----
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.prompt_label = QLabel("›")
        self.prompt_label.setFont(theme.font("mono", 14, bold=True))
        bar.addWidget(self.prompt_label)
        self.entry = QLineEdit()
        self.entry.setObjectName("CommandInput")
        self.entry.setPlaceholderText("Enter command or press the mic to speak…")
        self.entry.setMinimumHeight(34)
        bar.addWidget(self.entry, 1)
        self.mic_btn = QPushButton("MIC")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setMinimumHeight(34)
        self.mic_btn.setToolTip("Push to talk")
        bar.addWidget(self.mic_btn)
        self.send_btn = QPushButton("SEND")
        self.send_btn.setMinimumHeight(34)
        bar.addWidget(self.send_btn)
        root.addLayout(bar)

        self.settings_panel = SettingsPanel(self.settings, self)

    def _build_title(self):
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(34)
        row = QHBoxLayout(self.title_bar)
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(6)
        self.title_label = QLabel("H.I.N.A.")
        self.title_label.setFont(theme.font("display", 13, bold=True, spacing=4))
        row.addWidget(self.title_label)
        self.tagline = QLabel("HEURISTIC INTELLIGENT NEURAL ASSISTANT")
        self.tagline.setObjectName("Dim")
        row.addWidget(self.tagline)
        row.addStretch(1)
        self.title_status = QLabel()
        self.title_status.setObjectName("Caption")
        row.addWidget(self.title_status)
        row.addSpacing(8)

        self.yes_btn = QPushButton("CONFIRM")
        self.yes_btn.setObjectName("Yes")
        self.no_btn = QPushButton("DENY")
        self.no_btn.setObjectName("No")
        for b in (self.yes_btn, self.no_btn):
            b.hide()
            row.addWidget(b)

        def chrome(text, tip, name="Chrome"):
            b = QPushButton(text)
            b.setObjectName(name)
            b.setToolTip(tip)
            b.setFixedSize(28, 24)
            row.addWidget(b)
            return b

        self.compact_btn = chrome("◱", "Compact / expanded")
        self.gear_btn = chrome("⚙︎", "Settings")
        self.min_btn = chrome("—", "Hide (tray / hotkey brings it back)")
        self.close_btn = chrome("✕", "Shut down Hina", "Close")
        return self.title_bar

    def _wire(self):
        b = self.bridge
        self.entry.returnPressed.connect(self.execute_command)
        self.entry.textEdited.connect(self._touch)
        self.send_btn.clicked.connect(self.execute_command)
        self.mic_btn.clicked.connect(self.toggle_listening)
        self.yes_btn.clicked.connect(lambda: self.answer(True))
        self.no_btn.clicked.connect(lambda: self.answer(False))
        self.compact_btn.clicked.connect(lambda: self.set_compact(not self.compact))
        self.gear_btn.clicked.connect(self.toggle_settings)
        self.min_btn.clicked.connect(self.hide_window)
        self.close_btn.clicked.connect(self.quit_app)

        b.result_ready.connect(self._on_result)
        b.heard.connect(self._on_heard)
        b.voice_state.connect(self._on_voice_state)
        b.mic_level.connect(self.core.set_level)
        b.side_text.connect(lambda text: self.console.add_system(text))
        b.busy_changed.connect(lambda _: self.refresh_state())
        b.listening_changed.connect(self._on_listening_changed)
        b.mode_changed.connect(lambda m: self.status.mode.set(m, "active"))

        self.hotkey_toggle.connect(self.toggle_visibility)
        self.hotkey_talk.connect(self._hotkey_talk)
        self.ai_status.connect(self._on_ai_status)
        self.console.revealing_changed.connect(lambda _: self.refresh_state())

        self.settings_panel.saved.connect(self._on_settings_saved)
        self.settings_panel.memory_changed.connect(lambda text: self.console.add_system(text, "ok"))
        self.settings_panel.preview.connect(lambda s: self._apply_look(s))

    # =================================================================
    # commands
    # =================================================================
    def _touch(self, *_):
        self.last_activity = time.time()

    def execute_command(self):
        text = self.entry.text().strip()
        if not text or self.bridge.busy or self.bridge.listening:
            return False
        self.entry.clear()
        return self.start_command(text)

    def start_command(self, text):
        """Shared by typed and spoken input."""
        self._touch()
        if self._pending_exit and not self.bridge.busy:
            return self._resolve_exit(text)
        if not self.bridge.submit(text):
            return False
        self.console.add_user(text)
        self.show_confirm(False)
        self.refresh_state()
        return True

    def ask_exit(self, heard):
        """A spoken goodbye: ask before shutting down."""
        self._pending_exit = True
        self.console.add_user(heard)
        self.console.add_reply("Shut down Hina? Say yes or no.")
        self.show_confirm(True)

    def _resolve_exit(self, text):
        from core import permissions
        self._pending_exit = False
        self.show_confirm(False)
        answer = permissions.parse_answer(text)
        if answer is None:  # something else: drop the question and run it
            return self.start_command(text)
        self.console.add_user(text)
        if answer:
            return self.bridge.submit("bye")
        self.console.add_reply("Understood. Staying online.")
        return True

    def answer(self, yes):
        if self.bridge.busy:
            return False
        return self.start_command("yes" if yes else "no")

    def _on_result(self, result):
        self.show_confirm(bool(getattr(result, "needs_confirmation", False)))
        if result.reply:
            self.console.add_reply(result.reply)
            self.speak(result.reply)
        if getattr(result, "needs_confirmation", False):
            self.console.add_system("Awaiting confirmation.", "warn")
        if result.should_exit:
            QTimer.singleShot(result.exit_delay_ms or 1800, self.quit_app)
        self.refresh_state()

    def load_history(self, limit=HISTORY_ON_START):
        """Show the last few turns from earlier sessions (greyed) so the log survives restarts."""
        try:
            from core import memory_store
            turns = memory_store.recent_turns(limit=limit)
        except Exception as exc:
            logger.warning("Couldn't load history: %s", exc)
            return 0
        for turn in turns:
            try:
                when = datetime.fromisoformat(turn["ts"])
            except (TypeError, ValueError):
                when = None
            self.console.add_user(turn["user"], when=when, dim=True)
            self.console.add_reply(turn["reply"], when=when, dim=True)
        if turns:
            self.console.add_system(f"Restored {len(turns)} earlier exchanges.")
        return len(turns)

    def speak(self, text):
        if self._speak is not None:
            return self._speak(text)
        try:
            import voice
            voice.speak(theme.hud_text(text), blocking=False)
        except Exception:
            logger.exception("Speech failed")

    def show_confirm(self, show):
        self.yes_btn.setVisible(show)
        self.no_btn.setVisible(show)

    # =================================================================
    # voice
    # =================================================================
    def toggle_listening(self):
        self._touch()
        started = self.bridge.toggle_listening()
        if started:
            self.console.add_system("Audio channel open. Listening.")
        self.mic_btn.setChecked(self.bridge.listening)
        self.refresh_state()

    def _hotkey_talk(self):
        if not self.isVisible():
            self.show_window()
        self.toggle_listening()

    def _on_listening_changed(self, listening):
        self.mic_btn.setChecked(listening)
        self.status.mic.set("LIVE" if listening else "READY", "active" if listening else "ok")
        if not listening:
            self.voice_status = ""
            self.core.set_level(0.0)
        self.refresh_state()

    def _on_voice_state(self, name):
        self.voice_status = VOICE_STATE_TEXT.get(name, name.upper())
        self.refresh_state()

    def _on_heard(self, heard):
        if heard.cancelled:
            self.console.add_system("Listening cancelled.")
        elif heard.error:
            self.console.add_system(heard.error, "error")
            self.status.mic.set("ERROR", "bad")
        elif not heard.text:
            self.console.add_system("No speech detected. Try again.", "warn")
        elif is_exit_phrase(heard.text) and not self._pending_exit:
            self.ask_exit(heard.text)
        else:
            self.start_command(heard.text)
        self.refresh_state()

    # =================================================================
    # state / status
    # =================================================================
    def compute_state(self):
        if self.bridge.listening:
            return "listening"
        if self.bridge.busy:
            return "thinking"
        try:
            import voice
            speaking = voice.is_speaking()
        except Exception:
            speaking = False
        if speaking or self.console.is_revealing():
            return "speaking"
        return "idle"

    def refresh_state(self):
        self.set_state(self.compute_state())

    def set_state(self, state):
        self.core.set_state(state)
        if state != self.state or not self.state_label.text():
            self.state = state
        caption = STATE_CAPTIONS[state]
        self.state_label.setText(f"◇  {caption}  ◇")
        sub = self.voice_status if state == "listening" and self.voice_status else {
            "idle": "AWAITING INPUT", "listening": "RECEIVING AUDIO",
            "thinking": "ROUTING COMMAND", "speaking": "VOICE OUTPUT ACTIVE"}[state]
        self.sub_label.setText(sub)
        self.title_status.setText(caption)
        self.status.core.set(caption, "active" if state != "idle" else "ok")

    def check_ai(self):
        if self._quitting:
            return

        def run():
            try:
                import core.ai_engine as ai_engine
                ok = bool(ai_engine.ollama_available())
            except Exception:
                ok = False
            self.ai_status.emit(ok)
        threading.Thread(target=run, daemon=True).start()

    def _on_ai_status(self, ok):
        missing = None
        if not ok:
            try:
                import core.ai_engine as ai_engine
                missing = ai_engine.missing_model()
            except Exception:
                pass
        if missing:
            self.status.ai.set("NO MODEL", "warn")
            if missing != self._reported_missing_model:
                self._reported_missing_model = missing
                self.console.add_system(f"AI model {missing} isn't installed in Ollama. "
                                        f"Choose another in settings or run: ollama pull {missing}", "warn")
            return
        self.status.ai.set("ONLINE" if ok else "OFFLINE", "ok" if ok else "warn")
        if ok and self._reported_missing_model:
            self._reported_missing_model = None
            self.console.add_system("AI model online.", "ok")

    def _ambient_tick(self, now=None):
        minutes = int(self.settings.get("ambient_minutes") or 0)
        if minutes <= 0 or self.bridge.busy or self.bridge.listening:
            return False
        now = now or time.time()
        gap = minutes * 60
        if now - self.last_activity < gap or now - self.last_ambient < gap:
            return False
        if self.isActiveWindow() and self.entry.hasFocus() and self.entry.text():
            return False
        self.last_ambient = now
        self.console.add_reply(random.choice(AMBIENT_LINES))
        return True

    # =================================================================
    # settings / look
    # =================================================================
    def _apply_look(self, s):
        self.accent = theme.accent(s)
        self.setStyleSheet(theme.stylesheet(self.accent))
        for w in (self.core, self.console, self.clock_frame, self.sys_frame, self.status_frame,
                  self.tele_frame, self.console_frame, self.settings_panel):
            w.set_accent(self.accent)
        self.prompt_label.setStyleSheet(f"color: {self.accent.name()};")
        self.title_label.setStyleSheet(f"color: {self.accent.name()};")
        self.setWindowOpacity(float(s.get("opacity", 1.0)))
        self._bg_cache = None
        self.update()

    def apply_settings(self, s, first=False):
        old = self.settings
        self.settings = s
        self.bridge.settings = s
        settings_mod.apply_runtime(s)
        self._apply_look(s)
        self.status.model.set(s.get("ai_model", "?"), "dim")
        self.status.voice.set("LOCAL" if s.get("local_only") else "NEURAL", "ok")
        if first:
            self.status.mic.set("READY", "ok")
            self.status.mode.set("STANDARD", "dim")
            self.status.ai.set("CHECKING", "dim")
            return
        if bool(old.get("always_on_top")) != bool(s.get("always_on_top")):
            visible = self.isVisible()
            self._apply_flags()
            if visible:
                self.show()
        if (old.get("toggle_hotkey"), old.get("ptt_hotkey")) != (s.get("toggle_hotkey"), s.get("ptt_hotkey")) \
                and self._hotkey_handles:
            self.register_hotkeys()
        if old.get("whisper_model") != s.get("whisper_model") and not self.bridge.listening:
            self.bridge._speech = None  # rebuilt with the new model on next use

    def _on_settings_saved(self, s):
        s = dict(s, compact=self.compact, window_pos=self.settings.get("window_pos"))
        was_private = bool(self.settings.get("private_mode"))
        model_changed = self.settings.get("ai_model") != s.get("ai_model")
        self.apply_settings(s)
        settings_mod.save(s)
        self.console.add_system("Configuration saved.", "ok")
        if bool(s.get("private_mode")) != was_private:
            self.console.add_system("Private mode on: nothing new is recorded." if s.get("private_mode")
                                    else "Private mode off: history recording resumed.", "warn")
        if model_changed:
            # re-check now rather than leaving the old ONLINE / NO MODEL up until the next 15 s check
            self._reported_missing_model = None
            self.status.ai.set("CHECKING", "dim")
            self.console.add_system(f"AI model set to {s.get('ai_model')}.")
            self.check_ai()

    def toggle_settings(self):
        if self.settings_panel.open:
            self.settings_panel.cancel()
        else:
            self.settings_panel.slide_in(self.settings)

    def _apply_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.settings.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def save_settings(self):
        try:
            settings_mod.save(self.settings)
        except OSError as exc:
            logger.warning("Couldn't save settings: %s", exc)

    # =================================================================
    # window behaviour
    # =================================================================
    def set_compact(self, compact, save=True):
        self.compact = bool(compact)
        self.settings["compact"] = self.compact
        self.left_col.setVisible(not compact)
        self.tagline.setVisible(not compact)
        self.center_col.setFixedWidth(170 if compact else 16777215)
        if compact:
            self.center_col.setMinimumWidth(170)
        else:
            self.center_col.setMinimumWidth(300)
        self.console_frame.setMinimumWidth(300 if not compact else 260)
        self.compact_btn.setText("◳" if compact else "◱")
        w, h = COMPACT_SIZE if compact else EXPANDED_SIZE
        self.setFixedSize(w, h)
        self._bg_cache = None
        self.settings_panel.reposition()
        if save:
            self.save_settings()

    def _restore_position(self):
        pos = self.settings.get("window_pos")
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        if isinstance(pos, (list, tuple)) and len(pos) == 2 and all(isinstance(v, int) for v in pos):
            if geo is None or any(s.availableGeometry().contains(pos[0] + 40, pos[1] + 20)
                                  for s in QApplication.screens()):
                self.move(pos[0], pos[1])
                return
        if geo is not None:
            self.move(geo.center().x() - self.width() // 2, geo.bottom() - self.height() - 60)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self._save_pos_timer.start(600)

    def _save_position(self):
        self.settings["window_pos"] = [self.x(), self.y()]
        self.save_settings()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg_cache = None
        self.settings_panel.reposition()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 46:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
            self._drag_from = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_from", None) is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_from = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.settings_panel.open:
                self.settings_panel.cancel()
            else:
                self.hide_window()
            return
        super().keyPressEvent(event)

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.entry.setFocus()

    def hide_window(self):
        self.hide()

    def toggle_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide_window()
        else:
            self.show_window()

    def closeEvent(self, event):
        if not self._quitting and self.tray is not None:
            event.ignore()
            self.hide_window()
            return
        super().closeEvent(event)

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        for timer in (self._state_timer, self._ambient_timer, self._ai_timer, self._save_pos_timer):
            timer.stop()
        self._save_position() if self.isVisible() else self.save_settings()
        self.unregister_hotkeys()
        if self.tray is not None:
            self.tray.hide()
        self.quit_requested.emit()
        self.close()
        app = QApplication.instance()
        if app is not None and getattr(app, "_hina_owner", None) is self:
            app.quit()

    # ---- hotkeys / tray ---------------------------------------------
    def register_hotkeys(self):
        self.unregister_hotkeys()
        try:
            import keyboard
        except Exception as exc:
            logger.warning("Global hotkeys unavailable: %s", exc)
            return
        for combo, signal in ((self.settings.get("toggle_hotkey") or "ctrl+h", self.hotkey_toggle),
                              (self.settings.get("ptt_hotkey") or "ctrl+m", self.hotkey_talk)):
            try:
                # keyboard calls back on its own thread; emitting a signal hops to the GUI thread
                self._hotkey_handles.append(keyboard.add_hotkey(combo, signal.emit))
            except Exception as exc:
                logger.warning("Couldn't register hotkey %r: %s", combo, exc)
                self.console.add_system(f"Hotkey {combo} unavailable.", "warn")

    def unregister_hotkeys(self):
        if not self._hotkey_handles:
            return
        try:
            import keyboard
            remove = getattr(keyboard, "remove_hotkey", None)
            for handle in self._hotkey_handles:
                if remove is not None and handle is not None:
                    try:
                        remove(handle)
                    except Exception:
                        pass
        except Exception:
            pass
        self._hotkey_handles = []

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(make_icon(self.accent), self)
        tray.setToolTip("Hina")
        menu = QMenu()
        menu.addAction("Show / Hide", self.toggle_visibility)
        menu.addAction("Settings", lambda: (self.show_window(), self.settings_panel.slide_in(self.settings)))
        menu.addSeparator()
        menu.addAction("Quit Hina", self.quit_app)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.toggle_visibility() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        self._tray_menu = menu
        return tray

    # =================================================================
    # painting: the HUD backdrop
    # =================================================================
    def paintEvent(self, event):
        if self._bg_cache is None or self._bg_cache.size() != self.size() * self.devicePixelRatioF():
            self._bg_cache = self._render_backdrop()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._bg_cache)
        p.end()

    def _render_backdrop(self):
        dpr = self.devicePixelRatioF()
        pix = QPixmap(self.size() * dpr)
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        a = self.accent
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        shape = chamfer_path(r, 18)

        # base: near-black with a faint vertical gradient
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(6, 14, 24, 238))
        g.setColorAt(1, QColor(2, 6, 12, 246))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPolygon(shape)

        p.save()
        clip = r.adjusted(2, 2, -2, -2)
        p.setClipRect(clip)
        # glow behind the core
        if self.center_col.isVisible():
            cg = self.center_col.geometry()
            cc = QPointF(cg.center().x(), cg.center().y() - 10)
            rg = QRadialGradient(cc, max(cg.width(), cg.height()) * 0.7)
            rg.setColorAt(0, theme.with_alpha(a, 34))
            rg.setColorAt(1, theme.with_alpha(a, 0))
            p.setBrush(rg)
            p.drawRect(r)
        # grid
        p.setPen(QPen(theme.with_alpha(a, 11), 1))
        step = 24
        x = clip.left()
        while x < clip.right():
            p.drawLine(QPointF(x, clip.top()), QPointF(x, clip.bottom()))
            x += step
        y = clip.top()
        while y < clip.bottom():
            p.drawLine(QPointF(clip.left(), y), QPointF(clip.right(), y))
            y += step
        # scanlines
        p.setPen(QPen(QColor(0, 0, 0, 38), 1))
        y = clip.top()
        while y < clip.bottom():
            p.drawLine(QPointF(clip.left(), y), QPointF(clip.right(), y))
            y += 3
        p.restore()

        # outline + glow
        for width, alpha in ((7, 18), (3, 40), (1.2, 170)):
            p.setPen(QPen(theme.with_alpha(a, alpha), width))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(shape)
        # title underline and accents
        p.setPen(QPen(theme.with_alpha(a, 90), 1))
        p.drawLine(QPointF(r.left() + 14, 44), QPointF(r.right() - 14, 44))
        p.setPen(QPen(a, 3))
        p.drawLine(QPointF(r.left() + 18, r.top() + 0.5), QPointF(r.left() + 120, r.top() + 0.5))
        p.drawLine(QPointF(r.right() - 120, r.bottom() - 0.5), QPointF(r.right() - 18, r.bottom() - 0.5))
        # tick ruler along the bottom edge
        p.setPen(QPen(theme.with_alpha(a, 70), 1))
        x = r.left() + 30
        i = 0
        while x < r.right() - 140:
            h = 5 if i % 5 == 0 else 2.5
            p.drawLine(QPointF(x, r.bottom() - 3), QPointF(x, r.bottom() - 3 - h))
            x += 8
            i += 1
        p.end()
        return pix
