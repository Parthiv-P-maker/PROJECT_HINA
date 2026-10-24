"""
User settings for Hina, stored as JSON in the user data dir
(%APPDATA%\\ProjectHina\\settings.json, next to the action log).

Pure Python (no Qt) so the core code and tests can use it too.
`apply_runtime()` pushes the settings that are cheap to wire into the modules
that currently hard-code them.
"""

import json
import os

from utils.logger import get_logger
from utils.paths import user_data_dir

logger = get_logger(__name__)

DEFAULTS = {
    "ai_model": "qwen2.5:3b",
    "local_only": False,          # True: no cloud TTS (edge-tts) - offline pyttsx3 voice instead
    "tts_voice": "en-US-AriaNeural",
    "whisper_model": "auto",      # auto = small.en on GPU, base.en on CPU
    "toggle_hotkey": "ctrl+h",
    "ptt_hotkey": "ctrl+m",
    "accent": "#00e5ff",
    "opacity": 0.94,
    "always_on_top": True,
    "ambient_minutes": 5,         # 0 = ambient thoughts off
    "search_folders": [],
    "compact": False,
    "window_pos": None,           # [x, y]
    "show_on_start": True,
    "private_mode": False,        # True: don't record conversation history or new facts
}

SUGGESTED_MODELS = ["qwen2.5:3b", "qwen2.5:7b", "llama3.2:3b", "phi3:mini"]
WHISPER_MODELS = ["auto", "tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
TTS_VOICES = [
    "en-US-AriaNeural", "en-US-JennyNeural", "en-US-GuyNeural", "en-US-DavisNeural",
    "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-AU-NatashaNeural", "en-IN-NeerjaNeural",
]
ACCENTS = ["#00e5ff", "#3d8bff", "#00ffa3", "#ffb300", "#ff3d5a", "#b388ff"]


def settings_path():
    return os.path.join(user_data_dir(), "settings.json")


def _search_folders_path():
    return os.path.join(user_data_dir(), "search_folders.txt")


def _read_search_folders_file():
    try:
        with open(_search_folders_path(), encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip() and not line.startswith("#")]
    except OSError:
        return []


def _clean(data):
    """Merge onto the defaults, dropping unknown keys and wrong-typed values."""
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in data:
            continue
        value = data[key]
        if default is None or isinstance(value, type(default)) or (
                isinstance(default, float) and isinstance(value, int) and not isinstance(value, bool)):
            out[key] = value
    out["opacity"] = min(1.0, max(0.3, float(out["opacity"])))
    out["ambient_minutes"] = max(0, int(out["ambient_minutes"]))
    out["search_folders"] = [str(p) for p in out["search_folders"] if str(p).strip()]
    return out


def load():
    """Settings dict; a missing or broken file gives the defaults."""
    data = {}
    try:
        with open(settings_path(), encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            data = {}
    except FileNotFoundError:
        # first run: pick up folders configured the old way
        data = {"search_folders": _read_search_folders_file()}
    except (OSError, ValueError) as exc:
        logger.warning("Couldn't read settings, using defaults: %s", exc)
    return _clean(data)


def save(settings):
    """Write settings.json (and search_folders.txt, which file search reads)."""
    clean = _clean(settings)
    path = settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(clean, file, indent=2)
    os.replace(tmp, path)
    try:
        with open(_search_folders_path(), "w", encoding="utf-8") as file:
            file.write("# Managed by Hina settings\n")
            file.writelines(p + "\n" for p in clean["search_folders"])
    except OSError as exc:
        logger.warning("Couldn't write search folders: %s", exc)
    return clean


def apply_runtime(settings):
    """Push settings into modules that read module-level constants."""
    try:
        import core.ai_engine as ai_engine
        if settings.get("ai_model"):
            ai_engine.MODEL = settings["ai_model"]
    except Exception as exc:
        logger.warning("Couldn't apply AI model setting: %s", exc)
    try:
        import voice
        voice.VOICE = settings.get("tts_voice") or DEFAULTS["tts_voice"]
        if not hasattr(voice, "_HINA_EDGE_AVAILABLE"):
            voice._HINA_EDGE_AVAILABLE = voice._HAS_EDGE_TTS
        voice._HAS_EDGE_TTS = voice._HINA_EDGE_AVAILABLE and not settings.get("local_only")
    except Exception as exc:
        logger.warning("Couldn't apply voice settings: %s", exc)


def whisper_model_name(settings):
    """None means stt picks by hardware (or HINA_STT_MODEL)."""
    name = settings.get("whisper_model") or "auto"
    return None if name == "auto" else name
