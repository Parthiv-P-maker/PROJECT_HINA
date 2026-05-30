import subprocess
import threading
import time
import os
import webbrowser
from urllib.parse import quote
try:
    import psutil  # type: ignore[reportMissingModuleSource]
    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False

def open_app(app_name):
    common_apps = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "vscode": "code",
        "vs code": "code",
        "spotify": "spotify",
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "paint": "mspaint",
        "cmd": "cmd"
    }

    target = app_name.lower().strip()

    if target in common_apps:
        try:
            subprocess.Popen(f"start {common_apps[target]}", shell=True)
            return f"Opening {app_name} 🌸"
        except:
            return "Couldn't open app 🌸"

    file_result = search_and_open_file(app_name)
    if file_result != "File not found 🌸":
        return file_result

    try:
        subprocess.run(f"start {app_name}", shell=True)
        return f"Opening {app_name} 🌸"
    except:
        return f"Couldn't find {app_name} 🌸"
    
def close_app(app_name):
    try:
        subprocess.run(f"taskkill /IM {app_name}.exe /F", shell=True)
        return f"Closing {app_name} 🌸"
    except Exception as e:
        return f"Couldn't close {app_name}: {e}"
    
def restart_app(app_name):
    close_app(app_name)
    time.sleep(1)
    return open_app(app_name)

from datetime import datetime

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
        result = eval(expression)
        return f"The answer is {result} 🌸"
    except:
        return "Invalid calculation 🌸"
    
def find_file(file_name):
    for root, dirs, files in os.walk("C:\\"):
        if file_name in files:
            return f"Found at: {os.path.join(root, file_name)} 🌸"

    return "File not found 🌸"

def find_folder(folder_name):
    for root, dirs, files in os.walk("C:\\"):
        if folder_name in dirs:
            return f"Found at: {os.path.join(root, folder_name)} 🌸"

    return "Folder not found 🌸"

def search_and_open_file(file_name):
    for root, dirs, files in os.walk("C:\\"):
        for file in files:
            if file_name.lower() in file.lower():
                full_path = os.path.join(root, file)
                os.startfile(full_path)
                return f"Opening {file} 🌸"

    return "File not found 🌸"

timer_thread = None
timer_cancelled = False


def timer_finished(seconds):
    global timer_cancelled

    import time
    time.sleep(seconds)

    if not timer_cancelled:
        print("\nHina: Timer finished ⏰🌸")


def set_timer(seconds):
    global timer_thread, timer_cancelled

    timer_cancelled = False
    timer_thread = threading.Thread(target=timer_finished, args=(seconds,))
    timer_thread.start()

    return f"Timer set for {seconds} seconds 🌸"


def cancel_timer():
    global timer_cancelled

    timer_cancelled = True
    return "Timer cancelled 🌸"

def countdown(seconds):
    import time
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
        
        # Open ChatGPT.com with query in URL
        search_url = f"https://chatgpt.com/?q={quote(query)}"
        webbrowser.open(search_url)
        return f"Opening ChatGPT to search '{query}' 🌸"
    except Exception as e:
        return f"Couldn't open ChatGPT: {str(e)} 🌸"