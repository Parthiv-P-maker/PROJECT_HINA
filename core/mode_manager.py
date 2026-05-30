import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

APP_ALIASES = {
    "chatgpt": r"C:\Program Files\OpenAI\ChatGPT\ChatGPT.exe",
    "claude": r"C:\Program Files\Anthropic\Claude\Claude.exe",
    "vscode": "code",
    "spotify": "spotify",
    "notepad": "notepad",
    "cmd": "cmd",
}

_MODE_FILE = Path(__file__).resolve().parents[1] / "modes.json"

_CHATGPT_LOCATIONS = [
    r"C:\Program Files\OpenAI\ChatGPT\ChatGPT.exe",
    r"C:\Program Files (x86)\OpenAI\ChatGPT\ChatGPT.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\ChatGPT\ChatGPT.exe"),
]

_CLAUDE_LOCATIONS = [
    r"C:\Program Files\Anthropic\Claude\Claude.exe",
    r"C:\Program Files (x86)\Anthropic\Claude\Claude.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Claude\Claude.exe"),
]

MODE_SUCCESS_REPLIES = {
    "coding": "Coding workspace ready 🌸",
    "study": "Study environment prepared 🌸",
    "research": "Research workspace ready 🌸",
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Mode configuration file not found: {path}")
    with open(path, "r", encoding="utf-8") as mode_file:
        return json.load(mode_file)


def load_modes() -> Dict[str, Any]:
    modes = _load_json(_MODE_FILE)
    validate_modes(modes)
    return modes


def validate_modes(modes: Any) -> Dict[str, Any]:
    if not isinstance(modes, dict):
        raise ValueError("Mode configuration must be a JSON object.")

    for mode_name, mode_config in modes.items():
        if not isinstance(mode_config, dict):
            raise ValueError(f"Mode '{mode_name}' must be an object.")

        apps = mode_config.get("apps")
        if apps is None or not isinstance(apps, list):
            raise ValueError(f"Mode '{mode_name}' must contain an 'apps' list.")

        if "folders" in mode_config and not isinstance(mode_config["folders"], list):
            raise ValueError(f"Mode '{mode_name}' folders must be a list.")

        for app_item in apps:
            if not isinstance(app_item, str):
                raise ValueError(f"Mode '{mode_name}' app names must be strings.")

        for folder_item in mode_config.get("folders", []):
            if not isinstance(folder_item, str):
                raise ValueError(f"Mode '{mode_name}' folder paths must be strings.")

    return modes


def resolve_app_path(app_name: str) -> Optional[str]:
    target = app_name.lower().strip()
    alias_target = APP_ALIASES.get(target)
    if alias_target:
        return alias_target

    if target == "chatgpt":
        for candidate in _CHATGPT_LOCATIONS:
            if candidate and os.path.isfile(candidate):
                return candidate

    if target == "claude":
        for candidate in _CLAUDE_LOCATIONS:
            if candidate and os.path.isfile(candidate):
                return candidate

    return None


def _launch_path_or_command(command: str) -> Tuple[bool, str]:
    try:
        if os.path.isfile(command):
            subprocess.Popen(f'start "" "{command}"', shell=True)
        else:
            subprocess.Popen(f'start "" {command}', shell=True)
        return True, "success"
    except Exception as exc:
        logger.warning("Failed to launch '%s': %s", command, exc)
        return False, str(exc)


def launch_app(app_name: str) -> Tuple[bool, str]:
    target = app_name.strip()
    app_path = resolve_app_path(target)

    if app_path:
        success, error = _launch_path_or_command(app_path)
        if success:
            return True, f"Opened {target}"
        return False, f"Unable to open {target}: {error}"

    if target.lower() in {"chatgpt", "claude"}:
        return False, f"Could not find desktop app for {target}."

    success, error = _launch_path_or_command(target)
    if success:
        return True, f"Opened {target}"

    return False, f"Could not open {target}: {error}"


def open_folder(folder_path: str) -> Tuple[bool, str]:
    if not os.path.isdir(folder_path):
        logger.warning("Folder not found: %s", folder_path)
        return False, f"Folder not found: {folder_path}"

    try:
        os.startfile(folder_path)
        return True, f"Opened folder {folder_path}"
    except Exception as exc:
        logger.warning("Failed to open folder '%s': %s", folder_path, exc)
        return False, f"Could not open folder {folder_path}: {exc}"


def launch_mode(mode_name: str) -> str:
    if not mode_name:
        return "Please specify a workspace mode 🌸"

    try:
        modes = load_modes()
    except Exception as exc:
        logger.warning("Unable to load modes: %s", exc)
        return "Mode configuration could not be loaded 🌸"

    mode = modes.get(mode_name.lower())
    if mode is None:
        return f"Mode '{mode_name}' not found 🌸"

    app_results: List[str] = []
    folder_results: List[str] = []
    has_errors = False

    for app_name in mode.get("apps", []):
        success, message = launch_app(app_name)
        app_results.append(message)
        if not success:
            has_errors = True

    for folder_path in mode.get("folders", []):
        success, message = open_folder(folder_path)
        folder_results.append(message)
        if not success:
            has_errors = True

    if has_errors:
        details = "; ".join(app_results + folder_results)
        logger.warning("Mode '%s' launched with issues: %s", mode_name, details)
        return f"Mode '{mode_name}' launched with some issues. 🌸"

    return MODE_SUCCESS_REPLIES.get(mode_name.lower(), "Workspace mode ready 🌸")
