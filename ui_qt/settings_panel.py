"""Slide-in settings panel (gear button). Edits a copy; `saved` fires with the new dict."""

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

from ui_qt import settings as settings_mod
from ui_qt import theme
from ui_qt.hud import chamfer_path


class SettingsPanel(QWidget):
    saved = Signal(dict)
    preview = Signal(dict)     # live accent/opacity preview while editing
    closed = Signal()
    memory_changed = Signal(str)   # facts deleted / history cleared (acts at once, not on SAVE)

    WIDTH = 330

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPanel")
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.settings = dict(settings)
        self.accent = theme.accent(settings)
        self.open = False
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._anim_done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 14, 14)
        outer.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("SYSTEM CONFIGURATION")
        title.setObjectName("Caption")
        head.addWidget(title)
        head.addStretch(1)
        close = QPushButton("✕")
        close.setObjectName("Chrome")
        close.setToolTip("Close settings")
        close.clicked.connect(self.cancel)
        head.addWidget(close)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(0)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setObjectName("SettingsScroll")
        body = QWidget()
        body.setObjectName("SettingsBody")
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 6, 0)
        form.setVerticalSpacing(7)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.addItems(settings_mod.SUGGESTED_MODELS)
        form.addRow("AI MODEL (OLLAMA)", self.ai_model)

        self.local_only = QCheckBox("Local only (offline voice)")
        self.local_only.setToolTip("Never use the online voice: speak with the offline neural voice (Piper) "
                                   "if it's installed, else the Windows voice")
        form.addRow(self.local_only)

        self.tts_voice = QComboBox()
        self.tts_voice.setEditable(True)
        self.tts_voice.addItems(settings_mod.TTS_VOICES)
        form.addRow("TTS VOICE", self.tts_voice)

        self.whisper = QComboBox()
        self.whisper.addItems(settings_mod.WHISPER_MODELS)
        form.addRow("WHISPER MODEL", self.whisper)

        self.wake_word = QCheckBox("Wake word (listen in the background)")
        self.wake_word.setToolTip("Listen in the background for the wake phrase. The mic stays on while Hina runs; "
                                  "nothing is recorded or stored until the wake phrase is heard.")
        form.addRow(self.wake_word)
        self.wake_phrase = QComboBox()
        for key, text in settings_mod.WAKE_PHRASES:
            self.wake_phrase.addItem(text, key)
        form.addRow("WAKE PHRASE", self.wake_phrase)
        self.voice_barge_in = QCheckBox("Wake phrase interrupts Hina while she talks")
        self.voice_barge_in.setToolTip("Say the wake phrase over her to stop her and give a new command. "
                                       "Works best with headphones.")
        form.addRow(self.voice_barge_in)
        self.follow_up = QCheckBox("Keep listening after a spoken reply")
        self.follow_up.setToolTip("After answering something you said, Hina listens a few seconds more "
                                  "so you can follow up without the hotkey.")
        form.addRow(self.follow_up)

        self.toggle_hotkey = QLineEdit()
        form.addRow("SHOW / HIDE HOTKEY", self.toggle_hotkey)
        self.ptt_hotkey = QLineEdit()
        form.addRow("PUSH-TO-TALK HOTKEY", self.ptt_hotkey)

        accent_row = QWidget()
        ar = QHBoxLayout(accent_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(4)
        self.swatches = []
        for hex_ in settings_mod.ACCENTS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setToolTip(hex_)
            b.setStyleSheet(f"background:{hex_}; border:1px solid rgba(255,255,255,60);")
            b.clicked.connect(lambda _=False, h=hex_: self._set_accent(h))
            ar.addWidget(b)
            self.swatches.append(b)
        pick = QPushButton("…")
        pick.setFixedSize(26, 22)
        pick.setToolTip("Custom colour")
        pick.clicked.connect(self._pick_colour)
        ar.addWidget(pick)
        ar.addStretch(1)
        form.addRow("ACCENT", accent_row)

        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.valueChanged.connect(lambda v: self._preview(opacity=v / 100))
        form.addRow("OPACITY", self.opacity)

        self.on_top = QCheckBox("Always on top")
        form.addRow(self.on_top)

        self.ambient = QSpinBox()
        self.ambient.setRange(0, 240)
        self.ambient.setSuffix(" min")
        self.ambient.setSpecialValueText("off")
        form.addRow("AMBIENT THOUGHTS EVERY", self.ambient)

        self.folders = QPlainTextEdit()
        self.folders.setPlaceholderText("One folder per line, e.g. C:\\Users\\me\\Projects")
        self.folders.setFixedHeight(70)
        form.addRow("EXTRA SEARCH FOLDERS", self.folders)

        # ---- memory (core/memory_store.py) ----
        mem_title = QLabel("MEMORY")
        mem_title.setObjectName("Caption")
        form.addRow(mem_title)
        self.private_mode = QCheckBox("Private mode (don't record history or facts)")
        form.addRow(self.private_mode)
        self.facts = QListWidget()
        self.facts.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.facts.setFixedHeight(96)
        self.facts.setWordWrap(True)
        form.addRow("REMEMBERED FACTS", self.facts)
        mem_buttons = QHBoxLayout()
        self.delete_fact_btn = QPushButton("DELETE FACT")
        self.delete_fact_btn.setToolTip("Forget the selected facts")
        self.delete_fact_btn.clicked.connect(self.delete_selected_facts)
        self.clear_history_btn = QPushButton("CLEAR HISTORY")
        self.clear_history_btn.setToolTip("Delete the stored conversation history (click twice)")
        self.clear_history_btn.clicked.connect(self.clear_history)
        mem_buttons.addWidget(self.delete_fact_btn)
        mem_buttons.addWidget(self.clear_history_btn)
        mem_buttons.addStretch(1)
        form.addRow(mem_buttons)
        self.memory_info = QLabel("")
        self.memory_info.setObjectName("Dim")
        self._confirm_clear = False
        form.addRow(self.memory_info)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.clicked.connect(self.cancel)
        self.save_btn = QPushButton("SAVE")
        self.save_btn.clicked.connect(self.save)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        outer.addLayout(buttons)
        self.hide()

    # ---- values -----------------------------------------------------
    def load_values(self, settings):
        self.settings = dict(settings)
        s = self.settings
        self._fill_models(s["ai_model"])
        self.local_only.setChecked(bool(s["local_only"]))
        self.tts_voice.setCurrentText(s["tts_voice"])
        self.whisper.setCurrentText(s["whisper_model"])
        self.wake_word.setChecked(bool(s.get("wake_word")))
        at = self.wake_phrase.findData(s.get("wake_phrase") or "jarvis")
        self.wake_phrase.setCurrentIndex(max(0, at))
        self.follow_up.setChecked(bool(s.get("follow_up", True)))
        self.voice_barge_in.setChecked(bool(s.get("voice_barge_in", True)))
        self.toggle_hotkey.setText(s["toggle_hotkey"])
        self.ptt_hotkey.setText(s["ptt_hotkey"])
        self.opacity.blockSignals(True)
        self.opacity.setValue(int(round(s["opacity"] * 100)))
        self.opacity.blockSignals(False)
        self.on_top.setChecked(bool(s["always_on_top"]))
        self.ambient.setValue(int(s["ambient_minutes"]))
        self.folders.setPlainText("\n".join(s["search_folders"]))
        self.private_mode.setChecked(bool(s.get("private_mode")))
        self._accent = s["accent"]
        self.refresh_memory()

    def values(self):
        out = dict(self.settings)
        out.update(
            ai_model=self.model_name(),
            local_only=self.local_only.isChecked(),
            tts_voice=self.tts_voice.currentText().strip() or settings_mod.DEFAULTS["tts_voice"],
            whisper_model=self.whisper.currentText(),
            wake_word=self.wake_word.isChecked(),
            wake_phrase=self.wake_phrase.currentData() or "jarvis",
            follow_up=self.follow_up.isChecked(),
            voice_barge_in=self.voice_barge_in.isChecked(),
            toggle_hotkey=self.toggle_hotkey.text().strip().lower() or "ctrl+h",
            ptt_hotkey=self.ptt_hotkey.text().strip().lower() or "ctrl+m",
            accent=self._accent,
            opacity=self.opacity.value() / 100,
            always_on_top=self.on_top.isChecked(),
            ambient_minutes=self.ambient.value(),
            search_folders=[ln.strip() for ln in self.folders.toPlainText().splitlines() if ln.strip()],
            private_mode=self.private_mode.isChecked(),
        )
        return out

    # ---- memory -----------------------------------------------------
    def refresh_memory(self):
        from core import memory_store
        from tools.recall import display
        self._confirm_clear = False
        self.clear_history_btn.setText("CLEAR HISTORY")
        self.facts.clear()
        try:
            facts, turns = memory_store.list_facts(), memory_store.turn_count()
        except Exception as exc:
            self.memory_info.setText(f"Memory unavailable: {exc}")
            return
        for fact in facts:
            item = QListWidgetItem(display(fact["text"]))
            item.setData(Qt.UserRole, fact["id"])
            item.setToolTip(f"{fact['created']} ({fact['source']})")
            self.facts.addItem(item)
        self.memory_info.setText(f"{len(facts)} facts, {turns} exchanges stored")

    def delete_selected_facts(self):
        from core import memory_store
        ids = [item.data(Qt.UserRole) for item in self.facts.selectedItems()]
        if not ids:
            return 0
        memory_store.delete_facts(ids)
        self.refresh_memory()
        self.memory_changed.emit(f"Forgot {len(ids)} fact{'s' if len(ids) != 1 else ''}.")
        return len(ids)

    def clear_history(self):
        """First click arms it, second click clears."""
        if not self._confirm_clear:
            self._confirm_clear = True
            self.clear_history_btn.setText("CONFIRM CLEAR")
            return False
        from core import memory_store
        memory_store.clear_history()
        self.refresh_memory()
        self.memory_changed.emit("Conversation history cleared.")
        return True

    NOT_INSTALLED = " (not installed)"

    def _fill_models(self, current):
        """Installed models first; suggestions Ollama doesn't have are marked (they'd answer 404)."""
        installed = []
        try:
            import core.ai_engine as ai_engine
            installed = ai_engine.installed_models()
        except Exception:
            pass
        items = list(installed) or list(settings_mod.SUGGESTED_MODELS)
        if installed:
            items += [m + self.NOT_INSTALLED for m in settings_mod.SUGGESTED_MODELS if m not in installed]
        self.ai_model.clear()
        self.ai_model.addItems(items)
        self.ai_model.setToolTip("Installed in Ollama: " + (", ".join(installed) or "unknown (is Ollama running?)"))
        at = self.ai_model.findText(current)
        if at < 0:
            at = self.ai_model.findText(current + self.NOT_INSTALLED)
        if at >= 0:
            self.ai_model.setCurrentIndex(at)
        else:
            self.ai_model.setEditText(current)

    def model_name(self):
        name = self.ai_model.currentText().strip()
        if name.endswith(self.NOT_INSTALLED):
            name = name[:-len(self.NOT_INSTALLED)].strip()
        return name or settings_mod.DEFAULTS["ai_model"]

    def _set_accent(self, hex_):
        self._accent = hex_
        self._preview(accent=hex_)

    def _pick_colour(self):
        c = QColorDialog.getColor(QColor(self._accent), self, "Accent colour")
        if c.isValid():
            self._set_accent(c.name())

    def _preview(self, **changes):
        s = self.values()
        s.update(changes)
        self.preview.emit(s)

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    # ---- open / close -----------------------------------------------
    def _place(self, shown):
        p = self.parentWidget()
        top = 46
        self.resize(self.WIDTH, p.height() - top - 10)
        x = p.width() - self.WIDTH - 10 if shown else p.width() + 4
        return QPoint(x, top)

    def slide_in(self, settings, animate=True):
        self.load_values(settings)
        self.open = True
        start = self._place(False)
        end = self._place(True)
        self.show()
        self.raise_()
        if animate:
            self.move(start)
            self._anim.stop()
            self._anim.setStartValue(start)
            self._anim.setEndValue(end)
            self._anim.start()
        else:
            self.move(end)

    def slide_out(self, animate=True):
        if not self.open:
            return
        self.open = False
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self.pos())
            self._anim.setEndValue(self._place(False))
            self._anim.start()
        else:
            self.hide()
        self.closed.emit()

    def _anim_done(self):
        if not self.open:
            self.hide()

    def reposition(self):
        if self.open:
            self.move(self._place(True))

    def save(self):
        clean = settings_mod.save(self.values())
        self.settings = clean
        self.saved.emit(clean)
        self.slide_out()

    def cancel(self):
        self.preview.emit(self.settings)  # undo any live preview
        self.slide_out()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(theme.with_alpha(theme.BG, 240))
        p.setPen(QPen(theme.with_alpha(self.accent, 170), 1.2))
        p.drawPolygon(chamfer_path(r, 14))
        p.setPen(QPen(self.accent, 3))
        p.drawLine(r.topLeft() + QPointF(14, 0), r.topLeft() + QPointF(80, 0))
        p.end()
