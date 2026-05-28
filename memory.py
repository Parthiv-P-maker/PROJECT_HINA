import json

from utils.constants import MEMORY_PROFILE_PATH as PROFILE_PATH


def load_profile():
    try:
        with open(PROFILE_PATH, "r") as file:
            return json.load(file)
    except:
        return {}


def save_profile(profile):
    with open(PROFILE_PATH, "w") as file:
        json.dump(profile, file, indent=4)


# =========================
# NAME MEMORY
# =========================

def set_name(name):
    profile = load_profile()

    profile["name"] = name

    save_profile(profile)

    return f"I'll remember your name, {name} 🌸"


def get_name():
    profile = load_profile()
    return profile.get("name")


# =========================
# RECENT APPS
# =========================

def add_recent_app(app_name):
    profile = load_profile()

    recent_apps = profile.get("recent_apps", [])

    if app_name in recent_apps:
        recent_apps.remove(app_name)

    recent_apps.insert(0, app_name)

    recent_apps = recent_apps[:10]

    profile["recent_apps"] = recent_apps

    save_profile(profile)


def get_recent_apps():
    profile = load_profile()
    return profile.get("recent_apps", [])


# =========================
# RECENT FILES
# =========================

def add_recent_file(file_name):
    profile = load_profile()

    recent_files = profile.get("recent_files", [])

    if file_name in recent_files:
        recent_files.remove(file_name)

    recent_files.insert(0, file_name)

    recent_files = recent_files[:10]

    profile["recent_files"] = recent_files

    save_profile(profile)


def get_recent_files():
    profile = load_profile()
    return profile.get("recent_files", [])


# =========================
# FAVORITE APPS
# =========================

def set_favorite_app(label, app_name):
    profile = load_profile()

    favorites = profile.get("favorite_apps", {})

    favorites[label] = app_name

    profile["favorite_apps"] = favorites

    save_profile(profile)

    return f"{app_name} is now your favorite {label} 🌸"


def get_favorite_app(label):
    profile = load_profile()

    favorites = profile.get("favorite_apps", {})

    return favorites.get(label)