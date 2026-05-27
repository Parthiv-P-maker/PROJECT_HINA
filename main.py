from actions import (
    open_app,
    close_app,
    restart_app,
    tell_time,
    tell_date,
    battery_status,
    disk_usage,
    calculate,
    find_file,
    find_folder,
    search_and_open_file,
    set_timer,
    cancel_timer,
    countdown
)

from parser import normalize_command
from voice import speak

import random


def hina_reply(message):
    print("Hina:", message)
    speak(message)


startup_lines = [
    "Hina is awake and ready to help 🌸",
    "Welcome back! What shall we do today? 🎀",
    "Yay, Hina is here! 🌷",
    "Ready for another productive day? ✨",
    "Hina reporting in! Let's do our best 🌸"
]

goodbye_lines = [
    "Bye bye! Take care 🌸",
    "Hina is going to sleep now 🎀",
    "See you soon! 🌷",
    "Good work today! ✨",
    "Until next time 🌸"
]


startup_message = random.choice(startup_lines)
hina_reply(startup_message)


while True:
    raw_command = input("You: ").lower()
    command = normalize_command(raw_command)

    if command in ["bye", "exit"]:
        hina_reply(random.choice(goodbye_lines))
        break

    elif command.startswith("open file "):
        file_name = command.replace("open file ", "")
        hina_reply(search_and_open_file(file_name))

    elif command.startswith("open "):
        app = command.replace("open ", "")
        hina_reply(open_app(app))

    elif command.startswith("restart "):
        app = command.replace("restart ", "")
        hina_reply(restart_app(app))

    elif command.startswith("close "):
        app = command.replace("close ", "")
        hina_reply(close_app(app))

    elif command == "tell time":
        hina_reply(tell_time())

    elif command == "tell date":
        hina_reply(tell_date())

    elif command == "battery":
        hina_reply(battery_status())

    elif command == "disk usage":
        hina_reply(disk_usage())

    elif command.startswith("calculate "):
        expression = command.replace("calculate ", "")
        hina_reply(calculate(expression))

    elif command.startswith("find file "):
        file_name = command.replace("find file ", "")
        hina_reply(find_file(file_name))

    elif command.startswith("find folder "):
        folder_name = command.replace("find folder ", "")
        hina_reply(find_folder(folder_name))

    elif command.startswith("timer "):
        seconds = int(command.replace("timer ", ""))
        hina_reply(set_timer(seconds))

    elif command == "cancel timer":
        hina_reply(cancel_timer())

    elif command.startswith("countdown "):
        seconds = int(command.replace("countdown ", ""))
        hina_reply(countdown(seconds))

    elif command in ["hello", "hi"]:
        responses = [
            "Hello! 🌸",
            "Hi there! 🎀",
            "Welcome back! 🌷",
            "Hina is listening! ✨"
        ]
        hina_reply(random.choice(responses))

    elif command == "how are you":
        responses = [
            "I'm doing great! Ready to help 🌸",
            "Feeling cheerful as always 🎀",
            "All systems happy and running ✨"
        ]
        hina_reply(random.choice(responses))

    elif command == "who are you":
        responses = [
            "I'm Hina, your desktop assistant 🌸",
            "Project Hina at your service 🎀",
            "Your cheerful anime productivity companion ✨"
        ]
        hina_reply(random.choice(responses))

    elif command == "thanks":
        responses = [
            "You're welcome 🌸",
            "Happy to help 🎀",
            "Anytime! ✨"
        ]
        hina_reply(random.choice(responses))

    elif command == "what can you do":
        hina_reply(
            "I can open apps, close apps, restart apps, tell time and date, show battery and disk usage, calculate, find files and folders, open files, set timers, and do countdowns 🌸"
        )

    else:
        hina_reply("I don't understand that yet 🌸")