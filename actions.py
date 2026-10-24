import os
import threading
import time
import webbrowser
from datetime import datetime
from urllib.parse import quote

try:
    import psutil  # type: ignore[reportMissingModuleSource]
    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False

from core.mode_manager import APP_ALIASES
from utils.file_search import search as _search_files
from utils.launcher import launch, kill_process
from utils.safe_math import safe_eval

COMMON_APPS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "vscode": "code",
    "vs code": "code",
    "spotify": "spotify",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "cmd": "cmd",
}


def open_app(app_name):
    target = (app_name or "").lower().strip()
    if not target:
        return "Which app should I open? 🌸"

    command = APP_ALIASES.get(target) or COMMON_APPS.get(target)
    if command:
        ok, _ = launch(command)
        return f"Opening {app_name} 🌸" if ok else f"Couldn't open {app_name} 🌸"

    # Unknown name: try it as an app/command only. Files are opened with
    # "open file <name>", never by guessing.
    ok, _ = launch(target)
    if ok:
        return f"Opening {app_name} 🌸"
    return f"I couldn't find an app called {app_name}. Try 'open file {app_name}' if it's a file 🌸"


def close_app(app_name):
    ok, error = kill_process(app_name)
    if ok:
        return f"Closing {app_name} 🌸"
    return f"Couldn't close {app_name}: {error} 🌸"


def restart_app(app_name):
    close_app(app_name)
    time.sleep(1)
    return open_app(app_name)


def tell_time():
    current_time = datetime.now().strftime("%I:%M %p")
    return f"The time is {current_time} 🌸"


def tell_date():
    current_date = datetime.now().strftime("%d-%m-%Y")
    return f"Today's date is {current_date} 🌸"


def battery_status():
    if not _HAS_PSUTIL:
        return "Battery info not available (psutil not installed) 🌸"

    battery = psutil.sensors_battery()
    if battery is None:
        return "Battery info not available 🌸"

    percent = battery.percent
    charging = "charging" if battery.power_plugged else "not charging"

    return f"Battery is {percent}% and {charging} 🌸"


def disk_usage():
    if not _HAS_PSUTIL:
        return "Disk info not available (psutil not installed) 🌸"

    disk = psutil.disk_usage('/')

    free_gb = round(disk.free / (1024**3), 2)
    total_gb = round(disk.total / (1024**3), 2)

    return f"Disk space: {free_gb} GB free out of {total_gb} GB 🌸"


def calculate(expression):
    try:
        result = safe_eval(expression)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"The answer is {result} 🌸"
    except (ValueError, ZeroDivisionError, OverflowError):
        return "Invalid calculation 🌸"


def find_file(file_name):
    hits = _search_files(file_name, want="file")
    if hits:
        return f"Found at: {hits[0]} 🌸"
    return "File not found 🌸"


def find_folder(folder_name):
    hits = _search_files(folder_name, want="folder")
    if hits:
        return f"Found at: {hits[0]} 🌸"
    return "Folder not found 🌸"


def search_and_open_file(file_name):
    hits = _search_files(file_name, want="file")
    if not hits:
        return "File not found 🌸"
    try:
        os.startfile(hits[0])
    except OSError:
        return "Couldn't open that file 🌸"
    return f"Opening {os.path.basename(hits[0])} 🌸"


timer_thread = None
timer_cancelled = False


def timer_finished(seconds):
    global timer_cancelled

    time.sleep(seconds)

    if not timer_cancelled:
        print("\nHina: Timer finished ⏰🌸")


def set_timer(seconds):
    global timer_thread, timer_cancelled

    timer_cancelled = False
    timer_thread = threading.Thread(target=timer_finished, args=(seconds,), daemon=True)
    timer_thread.start()

    return f"Timer set for {seconds} seconds 🌸"


def cancel_timer():
    global timer_cancelled

    timer_cancelled = True
    return "Timer cancelled 🌸"


def countdown(seconds):
    import random

    cute_lines = [
        "Ready?",
        "Steady...",
        "Almost there...",
        "Just a little more...",
        "Don't blink...",
        "Hina is counting...",
        "Nearly done..."
    ]

    print("Hina: Countdown begins.")

    for i in range(seconds, 0, -1):
        line = random.choice(cute_lines)
        print(f"Hina: {i}... {line}")
        time.sleep(1)

    return "Done!"


def search_google(query):
    """Search Google for the given query in the default browser."""
    try:
        if not query or query.strip() == "":
            return "Please provide a search query 🌸"

        search_url = f"https://www.google.com/search?q={quote(query)}"
        webbrowser.open(search_url)
        return f"Searching Google for '{query}' 🌸"
    except Exception as e:
        return f"Couldn't open browser: {str(e)} 🌸"


def search_chatgpt(query):
    """Open ChatGPT with the given query."""
    try:
        if not query or query.strip() == "":
            return "Please provide a search query 🌸"

        search_url = f"https://chatgpt.com/?q={quote(query)}"
        webbrowser.open(search_url)
        return f"Opening ChatGPT to search '{query}' 🌸"
    except Exception as e:
        return f"Couldn't open ChatGPT: {str(e)} 🌸"
