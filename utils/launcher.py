"""
Safe process launching / killing.

Nothing here goes through a shell, so names coming from the user or from the
LLM can't smuggle in extra commands (e.g. "notepad & del ...").
"""

import os
import re
import shutil
import subprocess

from utils.logger import get_logger

logger = get_logger(__name__)

# Letters, digits, space, dot, dash, underscore, plus. Enough for app names.
_SAFE_NAME = re.compile(r"^[\w .+\-]{1,64}$")

# Friendly name -> process image name used by taskkill.
PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "code": "Code.exe",
    "spotify": "Spotify.exe",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "calc": "CalculatorApp.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "chatgpt": "ChatGPT.exe",
    "claude": "Claude.exe",
    "discord": "Discord.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
}

# Never allow these to be killed by name.
PROTECTED_PROCESSES = {
    "explorer.exe", "winlogon.exe", "csrss.exe", "lsass.exe", "services.exe",
    "svchost.exe", "smss.exe", "wininit.exe", "dwm.exe", "system",
}


def is_safe_name(name):
    return bool(name) and bool(_SAFE_NAME.match(name.strip()))


def launch(target):
    """
    Launch an exe path, a command on PATH, or a name Windows knows how to open
    (like `start <name>` would), without a shell. Returns (ok, error_message).
    """
    target = (target or "").strip()
    if not target:
        return False, "nothing to open"

    try:
        if os.path.isfile(target) or os.path.isdir(target):
            os.startfile(target)
            return True, ""

        if not is_safe_name(target):
            return False, f"'{target}' doesn't look like an app name"

        exe = shutil.which(target)
        if exe:
            subprocess.Popen([exe], close_fds=True)
            return True, ""

        # Same lookup as `start <name>`: App Paths registry, PATH, protocols.
        os.startfile(target)
        return True, ""
    except OSError as exc:
        logger.warning("Failed to launch '%s': %s", target, exc)
        return False, str(exc)
    except Exception as exc:
        logger.warning("Failed to launch '%s': %s", target, exc)
        return False, str(exc)


def process_name_for(app_name):
    """Map a friendly app name to its process image name, or None if unsafe."""
    target = (app_name or "").strip().lower()
    if target in PROCESS_NAMES:
        return PROCESS_NAMES[target]
    if not is_safe_name(target):
        return None
    return target if target.endswith(".exe") else f"{target}.exe"


def kill_process(app_name):
    """Close an app by name with taskkill (no shell). Returns (ok, error_message)."""
    proc = process_name_for(app_name)
    if proc is None:
        return False, f"'{app_name}' doesn't look like an app name"
    if proc.lower() in PROTECTED_PROCESSES:
        return False, f"{proc} is a system process"

    try:
        result = subprocess.run(
            ["taskkill", "/IM", proc, "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        logger.warning("taskkill failed for '%s': %s", proc, exc)
        return False, str(exc)

    if result.returncode != 0:
        return False, f"{app_name} isn't running"
    return True, ""
