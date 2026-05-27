import customtkinter as ctk
import keyboard
import random
import threading
import time

from parser import normalize_command
from actions import *
from voice import speak


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


# =========================
# HINA REPLY
# =========================

def hina_reply(message):
    output.configure(text=f"Hina: {message}")
    speak(message)


# =========================
# COUNTDOWN WITH VOICE
# =========================

def voiced_countdown(seconds):
    cute_lines = [
        "Ready?",
        "Steady...",
        "Almost there...",
        "Just a little more...",
        "Don't blink...",
        "Hina is counting...",
        "Nearly done..."
    ]

    for i in range(seconds, 0, -1):
        msg = f"{i}... {random.choice(cute_lines)}"
        output.configure(text=f"Hina: {msg}")
        speak(msg)
        time.sleep(1)

    hina_reply("Done!")


# =========================
# COMMAND EXECUTION
# =========================

def execute_command(event=None):
    raw_command = entry.get()
    command = normalize_command(raw_command)

    entry.delete(0, "end")

    # EXIT
    if command in ["bye", "exit"]:
        goodbye_lines = [
            "Bye bye! Take care 🌸",
            "Hina is going to sleep now 🎀",
            "See you soon! 🌷",
            "Good work today! ✨",
            "Until next time 🌸"
        ]

        hina_reply(random.choice(goodbye_lines))
        app.after(1800, app.destroy)
        return

    # FILES
    elif command.startswith("open file "):
        file_name = command.replace("open file ", "")
        hina_reply(search_and_open_file(file_name))

    elif command.startswith("find file "):
        file_name = command.replace("find file ", "")
        hina_reply(find_file(file_name))

    elif command.startswith("find folder "):
        folder_name = command.replace("find folder ", "")
        hina_reply(find_folder(folder_name))

    # APPS
    elif command.startswith("open "):
        app_name = command.replace("open ", "")
        hina_reply(open_app(app_name))

    elif command.startswith("close "):
        app_name = command.replace("close ", "")
        hina_reply(close_app(app_name))

    elif command.startswith("restart "):
        app_name = command.replace("restart ", "")
        hina_reply(restart_app(app_name))

    # SYSTEM
    elif command == "tell time":
        hina_reply(tell_time())

    elif command == "tell date":
        hina_reply(tell_date())

    elif command == "battery":
        hina_reply(battery_status())

    elif command == "disk usage":
        hina_reply(disk_usage())

    # CALCULATOR
    elif command.startswith("calculate "):
        expression = command.replace("calculate ", "")
        hina_reply(calculate(expression))

    # TIMER
    elif command.startswith("timer "):
        seconds = int(command.replace("timer ", ""))
        hina_reply(set_timer(seconds))

    elif command == "cancel timer":
        hina_reply(cancel_timer())

    # COUNTDOWN
    elif command.startswith("countdown "):
        seconds = int(command.replace("countdown ", ""))

        threading.Thread(
            target=voiced_countdown,
            args=(seconds,),
            daemon=True
        ).start()

    # CONVERSATION
    elif command in ["hello", "hi"]:
        hina_reply(random.choice([
            "Hello! 🌸",
            "Hi there! 🎀",
            "Welcome back! 🌷",
            "Hina is listening ✨"
        ]))

    elif command == "how are you":
        hina_reply(random.choice([
            "I'm doing great 🌸",
            "Feeling cheerful as always 🎀",
            "All systems happy and running ✨"
        ]))

    elif command == "who are you":
        hina_reply(random.choice([
            "I'm Hina, your desktop assistant 🌸",
            "Project Hina at your service 🎀",
            "Your cheerful anime productivity companion ✨"
        ]))

    elif command == "thanks":
        hina_reply(random.choice([
            "You're welcome 🌸",
            "Happy to help 🎀",
            "Anytime ✨"
        ]))

    elif command == "what can you do":
        hina_reply(
            "I can open apps, manage files, tell time and date, calculate, set timers, and more 🌸"
        )

    else:
        hina_reply("I don't understand that yet 🌸")


# =========================
# TOGGLE WINDOW
# =========================

def toggle_window():
    if app.state() == "withdrawn":
        app.deiconify()
        app.focus_force()
        entry.focus()
    else:
        app.withdraw()


# =========================
# APP
# =========================

app = ctk.CTk()

app.geometry("540x260")
app.title("Project Hina")
app.attributes("-topmost", True)
app.resizable(False, False)


# MAIN FRAME
frame = ctk.CTkFrame(
    app,
    corner_radius=20
)
frame.pack(
    padx=15,
    pady=15,
    fill="both",
    expand=True
)


# TITLE
title = ctk.CTkLabel(
    frame,
    text="Hina 🌸",
    font=("Segoe UI", 30, "bold")
)
title.pack(pady=(15, 10))


# OUTPUT
output = ctk.CTkLabel(
    frame,
    text="Hina is ready 🌸",
    wraplength=460,
    justify="center",
    font=("Segoe UI", 16)
)
output.pack(pady=10)


# ENTRY
entry = ctk.CTkEntry(
    frame,
    width=450,
    height=45,
    corner_radius=15,
    font=("Segoe UI", 18),
    placeholder_text="Talk to Hina..."
)
entry.pack(pady=15)

entry.bind("<Return>", execute_command)


# HOTKEY
keyboard.add_hotkey("ctrl+h", toggle_window)


# STARTUP GREETING
startup_message = random.choice([
    "Hina is awake and ready to help 🌸",
    "Welcome back! What shall we do today? 🎀",
    "Yay, Hina is here 🌷",
    "Ready for another productive day ✨",
    "Hina reporting in 🌸"
])

hina_reply(startup_message)


# START HIDDEN
app.after(2500, app.withdraw)

app.mainloop()