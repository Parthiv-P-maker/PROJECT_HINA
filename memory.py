"""
The user's profile (name, recent apps/files, favourites) as JSON.

Lives in the user data dir (%APPDATA%\\ProjectHina\\user_profile.json, or
HINA_DATA_DIR). The old in-repo memory/user_profile.json is copied there once,
on first use. Saves are atomic (temp file + os.replace) and every
read-modify-write runs under one lock, so two threads can't lose an update.
A file that won't parse is kept as `user_profile.json.corrupt` and logged.
"""

import json
import os
import shutil
import threading
from datetime import datetime

from utils.constants import MEMORY_PROFILE_PATH as LEGACY_PROFILE_PATH
from utils.logger import get_logger
from utils.paths import user_data_dir

logger = get_logger(__name__)

PROFILE_FILE = "user_profile.json"
# None = <user data dir>/user_profile.json. Tests point this at a temp file.
PROFILE_PATH = None

_lock = threading.RLock()


def profile_path():
    if PROFILE_PATH:
        return PROFILE_PATH
    path = os.path.join(user_data_dir(), PROFILE_FILE)
    _migrate_legacy(path)
    return path


def _migrate_legacy(path):
    """Copy the old in-repo profile into the data dir, once (when there is none yet)."""
    if os.path.exists(path) or not LEGACY_PROFILE_PATH or not os.path.exists(LEGACY_PROFILE_PATH):
        return
    try:
        shutil.copyfile(LEGACY_PROFILE_PATH, path)
        logger.info("Migrated profile from %s to %s", LEGACY_PROFILE_PATH, path)
    except OSError as exc:
        logger.warning("Couldn't migrate old profile %s: %s", LEGACY_PROFILE_PATH, exc)


def _quarantine(path, reason):
    """Move an unreadable profile aside as *.corrupt so the user's data isn't overwritten."""
    target = path + ".corrupt"
    if os.path.exists(target):
        target = f"{path}.{datetime.now():%Y%m%d-%H%M%S}.corrupt"
    try:
        os.replace(path, target)
        logger.error("Profile %s is corrupt (%s); kept a copy as %s", path, reason, target)
    except OSError as exc:
        logger.error("Profile %s is corrupt (%s) and couldn't be moved aside: %s", path, reason, exc)


def load_profile():
    with _lock:
        path = profile_path()
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            return {}
        except (ValueError, UnicodeDecodeError) as exc:
            _quarantine(path, exc)
            return {}
        except OSError as exc:
            logger.warning("Couldn't read profile %s: %s", path, exc)
            return {}
        if not isinstance(data, dict):
            _quarantine(path, "not a JSON object")
            return {}
        return data


def save_profile(profile):
    with _lock:
        path = profile_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as file:
                json.dump(profile, file, indent=4)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def update_profile(change):
    """Load, let `change(profile)` edit it in place, save; all under the lock. Returns its result."""
    with _lock:
        profile = load_profile()
        result = change(profile)
        save_profile(profile)
        return result


# =========================
# NAME MEMORY
# =========================

def set_name(name):
    update_profile(lambda profile: profile.__setitem__("name", name))
    return f"I'll remember your name, {name} 🌸"


def get_name():
    return load_profile().get("name")


def set_personality(name):
    update_profile(lambda profile: profile.__setitem__("personality", name))


def get_personality():
    return load_profile().get("personality")


# =========================
# RECENT LISTS
# =========================

def _push_recent(key, item, limit=10):
    def change(profile):
        items = [x for x in profile.get(key, []) if x != item]
        profile[key] = ([item] + items)[:limit]
    update_profile(change)


def add_recent_app(app_name):
    _push_recent("recent_apps", app_name)


def get_recent_apps():
    return load_profile().get("recent_apps", [])


def add_recent_file(file_name):
    _push_recent("recent_files", file_name)


def get_recent_files():
    return load_profile().get("recent_files", [])


# =========================
# FAVORITE APPS
# =========================

def set_favorite_app(label, app_name):
    update_profile(lambda profile: profile.setdefault("favorite_apps", {}).__setitem__(label, app_name))
    return f"{app_name} is now your favorite {label} 🌸"


def get_favorite_app(label):
    return load_profile().get("favorite_apps", {}).get(label)
