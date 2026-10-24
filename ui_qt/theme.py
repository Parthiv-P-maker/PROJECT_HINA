"""HUD palette, fonts and the Qt stylesheet. Everything keys off one accent colour."""

import os
import re

from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = QColor(4, 8, 14)
BG_PANEL = QColor(8, 16, 26)
TEXT = QColor(200, 236, 255)
TEXT_DIM = QColor(96, 140, 165)
WARN = QColor(255, 179, 0)
DANGER = QColor(255, 61, 90)
OK = QColor(0, 255, 163)

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_loaded = False

# First family that exists wins; drop Orbitron / Rajdhani / JetBrains Mono .ttf
# files into ui_qt/fonts/ and they are picked up automatically.
DISPLAY_FAMILIES = ["Orbitron", "Rajdhani", "Bahnschrift", "Segoe UI Semibold", "Arial"]
TEXT_FAMILIES = ["Rajdhani", "Bahnschrift", "Segoe UI", "Arial"]
MONO_FAMILIES = ["JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New"]


def load_fonts():
    global _loaded
    if _loaded:
        return
    _loaded = True
    if os.path.isdir(_FONT_DIR):
        for name in os.listdir(_FONT_DIR):
            if name.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(_FONT_DIR, name))


def _pick(families):
    load_fonts()
    available = set(QFontDatabase.families())
    for family in families:
        if family in available:
            return family
    return families[-1]


def font(kind="text", size=10, bold=False, spacing=0.0):
    family = _pick({"display": DISPLAY_FAMILIES, "mono": MONO_FAMILIES}.get(kind, TEXT_FAMILIES))
    f = QFont(family)
    f.setPointSizeF(size)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def accent(settings_or_hex):
    value = settings_or_hex.get("accent") if isinstance(settings_or_hex, dict) else settings_or_hex
    color = QColor(value or "#00e5ff")
    return color if color.isValid() else QColor("#00e5ff")


def with_alpha(color, alpha):
    c = QColor(color)
    c.setAlpha(int(max(0, min(255, alpha))))
    return c


def rgba(color, alpha=255):
    return f"rgba({color.red()},{color.green()},{color.blue()},{int(alpha)})"


# Decorative emoji from the old anime persona; stripped from text shown in the HUD.
_CUTE = re.compile("[\U0001F338\U0001F380\U0001F337✨\U0001F496\U0001F495\U0001F497"
                   "\U0001F33A\U0001F33C\U0001F60A\U0001F970\U0001F49E❤️\U0001F3A4]")


def hud_text(text):
    return re.sub(r"\s{2,}", " ", _CUTE.sub("", text or "")).strip()


def stylesheet(acc):
    a = acc
    mono = _pick(MONO_FAMILIES)
    txt = _pick(TEXT_FAMILIES)
    return f"""
    QWidget {{ color: {rgba(TEXT)}; font-family: "{txt}"; }}
    QToolTip {{ background: {rgba(BG_PANEL)}; color: {rgba(TEXT)}; border: 1px solid {rgba(a, 160)}; }}
    QLineEdit#CommandInput {{
        background: {rgba(a, 14)}; border: 1px solid {rgba(a, 90)}; border-radius: 2px;
        padding: 6px 10px; font-family: "{mono}"; font-size: 11pt; color: {rgba(TEXT)};
        selection-background-color: {rgba(a, 120)};
    }}
    QLineEdit#CommandInput:focus {{ border: 1px solid {rgba(a, 230)}; background: {rgba(a, 24)}; }}
    QPushButton {{
        background: {rgba(a, 18)}; border: 1px solid {rgba(a, 110)}; border-radius: 2px;
        padding: 4px 10px; color: {rgba(a)}; font-family: "{mono}"; font-size: 9pt; letter-spacing: 1px;
    }}
    QPushButton:hover {{ background: {rgba(a, 50)}; border-color: {rgba(a, 230)}; }}
    QPushButton:pressed {{ background: {rgba(a, 90)}; }}
    QPushButton:checked {{ background: {rgba(a, 110)}; color: {rgba(BG)}; }}
    QPushButton#Chrome, QPushButton#Close {{ background: transparent; border: 1px solid transparent; padding: 0;
        font-family: "Segoe UI Symbol", "{txt}"; font-size: 10pt; }}
    QPushButton#Chrome:hover, QPushButton#Chrome:checked {{ border: 1px solid {rgba(a, 150)}; background: {rgba(a, 30)}; }}
    QPushButton#Close:hover {{ border: 1px solid {rgba(DANGER)}; background: {rgba(DANGER, 60)}; color: {rgba(TEXT)}; }}
    QPushButton#Yes {{ background: {rgba(OK, 40)}; border-color: {rgba(OK, 200)}; color: {rgba(OK)}; }}
    QPushButton#Yes:hover {{ background: {rgba(OK, 90)}; }}
    QPushButton#No {{ background: {rgba(DANGER, 30)}; border-color: {rgba(DANGER, 200)}; color: {rgba(DANGER)}; }}
    QPushButton#No:hover {{ background: {rgba(DANGER, 80)}; }}
    QTextBrowser#Console {{
        background: transparent; border: none; font-family: "{mono}"; font-size: 10pt;
        selection-background-color: {rgba(a, 110)};
    }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {rgba(a, 90)}; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; height: 0; }}
    QLabel#Caption {{ color: {rgba(a, 200)}; font-family: "{mono}"; font-size: 8pt; letter-spacing: 2px; }}
    QLabel#Dim {{ color: {rgba(TEXT_DIM)}; font-family: "{mono}"; font-size: 8pt; }}
    #SettingsScroll, #SettingsScroll > QWidget, #SettingsBody {{ background: rgb(5,11,19); border: none; }}
    #SettingsPanel QLineEdit, #SettingsPanel QComboBox, #SettingsPanel QSpinBox, #SettingsPanel QPlainTextEdit {{
        background: {rgba(a, 14)}; border: 1px solid {rgba(a, 80)}; border-radius: 2px; padding: 3px 6px;
        font-family: "{mono}"; font-size: 9pt; color: {rgba(TEXT)};
    }}
    #SettingsPanel QComboBox QAbstractItemView {{ background: {rgba(BG_PANEL)}; selection-background-color: {rgba(a, 110)}; }}
    #SettingsPanel QLabel {{ font-family: "{mono}"; font-size: 8pt; color: {rgba(TEXT_DIM)}; letter-spacing: 1px; }}
    #SettingsPanel QCheckBox {{ font-family: "{mono}"; font-size: 9pt; spacing: 8px; }}
    #SettingsPanel QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid {rgba(a, 160)}; background: transparent; }}
    #SettingsPanel QCheckBox::indicator:checked {{ background: {rgba(a)}; }}
    QSlider::groove:horizontal {{ height: 2px; background: {rgba(a, 70)}; }}
    QSlider::handle:horizontal {{ width: 10px; margin: -6px 0; background: {rgba(a)}; }}
    QMenu {{ background: {rgba(BG_PANEL)}; border: 1px solid {rgba(a, 140)}; font-family: "{mono}"; }}
    QMenu::item:selected {{ background: {rgba(a, 80)}; }}
    """
