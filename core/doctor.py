"""
Hina's self-check: `python hina.py --doctor`, or say "run a self-check".

Each check looks at one thing Hina depends on and says OK, WARN (works, with
something missing) or FAIL (a feature is broken), plus the exact fix. Checks
only read state: nothing is installed, downloaded, recorded or changed.
"""

import importlib
import importlib.util
import os
import sys
import time
from dataclasses import dataclass

OK, WARN, FAIL = "ok", "warn", "fail"

# pip name -> (module to import, what breaks without it, required?)
PACKAGES = [
    ("PySide6", "PySide6", "the main HUD", True),
    ("requests", "requests", "everything that talks to Ollama or the web", True),
    ("psutil", "psutil", "battery, disk, apps and windows", True),
    ("keyboard", "keyboard", "the global hotkeys", True),
    ("numpy", "numpy", "voice input", True),
    ("sounddevice", "sounddevice", "the microphone", True),
    ("faster-whisper", "faster_whisper", "speech-to-text and the wake word", True),
    ("edge-tts", "edge_tts", "the neural voice", False),
    ("pygame", "pygame", "playing the neural voice", False),
    ("pyttsx3", "pyttsx3", "the offline voice", False),
    ("pywin32", "win32gui", "clipboard, window control, Spotify's current track", True),
    ("comtypes", "comtypes", "exact volume control", False),
    ("PyMuPDF", "fitz", "questions about PDFs", False),
    ("customtkinter", "customtkinter", "the classic window (--classic)", False),
]


@dataclass
class Check:
    area: str
    status: str
    detail: str
    fix: str = ""


def _safe(area, fn):
    """Run one check; an unexpected error is itself a result, never a crash of the whole report."""
    try:
        return fn()
    except Exception as exc:
        return [Check(area, FAIL, f"the check itself failed: {type(exc).__name__}: {exc}")]


def check_python():
    v = sys.version_info
    ok = v >= (3, 10)
    return [Check("Python", OK if ok else FAIL, f"{v.major}.{v.minor}.{v.micro} ({sys.executable})",
                  "" if ok else "Install Python 3.10 or newer.")]


def check_packages():
    """Installed or not, found without importing (importing them all takes several seconds).
    The checks after this one import the important ones for real."""
    out = []
    for pip_name, module, feature, required in PACKAGES:
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if found:
            out.append(Check(f"Package {pip_name}", OK, "installed"))
        else:
            out.append(Check(f"Package {pip_name}", FAIL if required else WARN,
                             f"missing, so {feature} won't work", f"pip install {pip_name}"))
    return out


def check_ollama(settings):
    from core import ai_engine
    ai_engine._health["checked_at"] = 0.0  # a fresh look, not the cached answer
    if not ai_engine.ollama_available() and not ai_engine._health.get("ok"):
        return [Check("Ollama", FAIL, "not reachable at localhost:11434, so chat and AI commands are off",
                      "Start Ollama (the tray app, or run: ollama serve).")]
    models = ai_engine.installed_models()
    out = [Check("Ollama", OK, f"running, {len(models)} models: {', '.join(models) or 'none'}")]
    wanted = settings.get("ai_model") or ai_engine.MODEL
    out.append(Check("AI model", OK if ai_engine.model_installed(wanted) else FAIL,
                     f"{wanted} ({'installed' if ai_engine.model_installed(wanted) else 'not installed'})",
                     "" if ai_engine.model_installed(wanted) else f"ollama pull {wanted}"))
    smart = settings.get("smart_model")
    if smart:
        there = ai_engine.model_installed(smart)
        out.append(Check("Chat model", OK if there else WARN,
                         f"{smart} ({'installed' if there else 'not installed, the fast model is used instead'})",
                         "" if there else f"ollama pull {smart}"))
    there = ai_engine.model_installed(ai_engine.EMBED_MODEL)
    out.append(Check("Recall by meaning", OK if there else WARN,
                     f"{ai_engine.EMBED_MODEL} {'installed' if there else 'not installed, keyword matching is used'}",
                     "" if there else f"ollama pull {ai_engine.EMBED_MODEL}"))
    return out


def check_microphone():
    import sounddevice as sd
    from core import stt
    try:
        device = stt._resolve_device(sd)
        info = sd.query_devices(device, kind="input")
    except Exception as exc:
        return [Check("Microphone", FAIL, f"no input device found ({exc})",
                      "Plug in or enable a microphone in Windows Sound settings, or set HINA_MIC_DEVICE.")]
    return [Check("Microphone", OK, f"{info['name']} ({int(info['default_samplerate'])} Hz)",
                  "Run 'python -m core.stt' to watch its live level.")]


def check_speech_models():
    from core import stt
    gpu = stt._gpu_available()
    model = stt.MODEL_NAME or (stt.GPU_MODEL if gpu else stt.CPU_MODEL)
    out = [Check("Speech-to-text", OK, f"Whisper {model} on {'GPU (CUDA)' if gpu else 'CPU'}"
                 + ("" if gpu else "; a CUDA GPU makes it several times faster"))]
    vad = stt.load_vad()
    out.append(Check("Voice detection", OK if vad else WARN,
                     "Silero VAD loaded" if vad else "Silero VAD unavailable, loudness is used instead",
                     "" if vad else "pip install onnxruntime"))
    return out


def check_voice(settings):
    import voice
    neural = getattr(voice, "_HINA_EDGE_AVAILABLE", voice._HAS_EDGE_TTS) and voice._HAS_PYGAME
    if settings.get("local_only"):
        return [Check("Voice", OK, "offline voice (local only is on in settings)")]
    if neural:
        return [Check("Voice", OK, f"neural voice {settings.get('tts_voice') or voice.VOICE} "
                                    "(needs internet; falls back to the offline voice)")]
    return [Check("Voice", WARN, "neural voice unavailable, the offline voice is used",
                  "pip install edge-tts pygame")]


def check_windows_features():
    out = []
    from utils import device
    try:
        level, muted = device.get_volume()
        out.append(Check("Volume control", OK, f"volume {level}%{' (muted)' if muted else ''}"))
    except device.DeviceError as exc:
        out.append(Check("Volume control", WARN, f"{exc} Volume keys are used instead.", "pip install comtypes"))
    try:
        out.append(Check("Brightness", OK, f"{device.get_brightness()}%"))
    except device.DeviceError:
        out.append(Check("Brightness", WARN, "this screen doesn't allow brightness control "
                                              "(normal for external monitors)"))
    try:
        from utils import windows
        out.append(Check("Window control", OK, f"{len(windows.list_windows())} app windows visible"))
    except Exception as exc:
        out.append(Check("Window control", FAIL, str(exc), "pip install pywin32"))
    return out


def check_data():
    from core import memory_store
    from utils import file_index
    from utils.logger import log_path
    from utils.paths import user_data_dir
    folder = user_data_dir()
    writable = os.access(folder, os.W_OK)
    out = [Check("Data folder", OK if writable else FAIL, folder,
                 "" if writable else "Make the folder writable or set HINA_DATA_DIR.")]
    out.append(Check("Memory", OK, f"{memory_store.turn_count()} exchanges, {len(memory_store.list_facts())} facts, "
                                   f"{len(memory_store.pending_reminders())} reminders"))
    files, stamp = file_index.count(), file_index.last_refresh()
    out.append(Check("File index", OK if files else WARN,
                     f"{files} files" + (f", scanned {stamp:%d %b %H:%M}" if stamp else ", never scanned"),
                     "" if files else 'Say "refresh file index", or just start Hina (it scans in the background).'))
    out.append(Check("Log file", OK, log_path()))
    return out


def check_settings(settings):
    wake_bit = f"wake word {'on' if settings.get('wake_word') else 'off'}"
    try:
        from core import wake
        wake_bit += f" ({wake.label(settings.get('wake_phrase'))})"
    except (ImportError, AttributeError):
        pass  # a build without the wake word
    bits = [
        wake_bit,
        f"follow-up {'on' if settings.get('follow_up', True) else 'off'}",
        f"private mode {'on' if settings.get('private_mode') else 'off'}",
        f"news region {settings.get('news_region', 'IN')}",
    ]
    return [Check("Settings", OK, ", ".join(bits))]


def run_checks(settings=None, hardware=True):
    """All checks, in reading order. hardware=False skips the mic, speech models and Windows controls."""
    if settings is None:
        from ui_qt import settings as settings_mod
        settings = settings_mod.load()
    results = []
    steps = [("Python", check_python), ("Packages", check_packages),
             ("Ollama", lambda: check_ollama(settings))]
    if hardware:
        steps += [("Microphone", check_microphone), ("Speech-to-text", check_speech_models),
                  ("Voice", lambda: check_voice(settings)), ("Windows", check_windows_features)]
    steps += [("Data", check_data), ("Settings", lambda: check_settings(settings))]
    for area, fn in steps:
        results.extend(_safe(area, fn))
    return results


def summary(results):
    """One spoken-length line: counts plus the first problems."""
    fails = [r for r in results if r.status == FAIL]
    warns = [r for r in results if r.status == WARN]
    if not fails and not warns:
        return f"All {len(results)} checks passed. Everything I need is in place."
    parts = []
    if fails:
        parts.append(f"{len(fails)} problem{'s' if len(fails) > 1 else ''}: "
                     + "; ".join(f"{r.area} ({r.fix or r.detail})" for r in fails[:3]))
    if warns:
        parts.append(f"{len(warns)} warning{'s' if len(warns) > 1 else ''}: " + ", ".join(r.area for r in warns[:4]))
    return " ".join(parts) + ". Run 'python hina.py --doctor' for the full report."


_LABEL = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}


def report(results):
    """The full report as plain ASCII-safe text (works in any Windows console)."""
    width = max(len(r.area) for r in results)
    lines = ["Project Hina self-check", "=" * 23, ""]
    for r in results:
        lines.append(f"{_LABEL[r.status]} {r.area.ljust(width)}  {r.detail}")
        if r.fix and r.status != OK:
            lines.append(f"{' ' * 7}{' ' * width}  -> {r.fix}")
    fails = sum(r.status == FAIL for r in results)
    warns = sum(r.status == WARN for r in results)
    lines += ["", f"{len(results)} checks: {len(results) - fails - warns} ok, {warns} warnings, {fails} problems."]
    return "\n".join(lines)


def main():
    started = time.time()
    results = run_checks()
    text = report(results) + f"\n(took {time.time() - started:.1f}s)"
    try:
        print(text)
    except UnicodeEncodeError:  # a device name the console can't show
        print(text.encode("ascii", "replace").decode("ascii"))
    return 1 if any(r.status == FAIL for r in results) else 0
