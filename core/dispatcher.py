import random
import threading
from dataclasses import dataclass

from actions import (
    open_app,
    search_and_open_file,
    find_folder,
    close_app,
    restart_app,
    tell_time,
    tell_date,
    battery_status,
    disk_usage,
    calculate,
    set_timer,
    cancel_timer,
)
from core.assistant import generate_response
from core.countdown import voiced_countdown
from core.startup import build_goodbye_message
from memory import (
    set_name,
    add_recent_app,
    add_recent_file,
    set_favorite_app,
    get_favorite_app,
)
from utils.helpers import try_parse_int
from utils.constants import EXIT_DELAY_MS


@dataclass
class DispatchResult:
    reply: str = ""
    should_exit: bool = False
    exit_delay_ms: int = 0


def dispatch_command(command, output_var=None, output_label=None, app=None):
    """Route a normalized command to the appropriate action handler."""
    if command.startswith("set name "):
        name = command.replace("set name ", "").strip()
        return DispatchResult(reply=set_name(name))

    if command in ["bye", "exit"]:
        return DispatchResult(
            reply=build_goodbye_message(),
            should_exit=True,
            exit_delay_ms=EXIT_DELAY_MS,
        )

    if command.startswith("open file "):
        file_name = command.replace("open file ", "").strip()
        add_recent_file(file_name)
        return DispatchResult(reply=search_and_open_file(file_name))

    if command.startswith("open "):
        app_name = command.replace("open ", "").strip()
        favorite_app = get_favorite_app(app_name)
        if favorite_app:
            app_name = favorite_app
        add_recent_app(app_name)
        open_app(app_name)
        return DispatchResult(reply=generate_response("open_app", app_name))

    if command.startswith("find folder "):
        return DispatchResult(reply=find_folder(command.replace("find folder ", "")))

    if command.startswith("favorite app "):
        data = command.replace("favorite app ", "").split(" as ")
        if len(data) == 2:
            app_name = data[0].strip()
            label = data[1].strip()
            return DispatchResult(reply=set_favorite_app(label, app_name))
        return DispatchResult(reply="Use: favorite app chrome as browser 🌸")

    if command.startswith("close "):
        app_name = command.replace("close ", "")
        close_app(app_name)
        return DispatchResult(reply=generate_response("close_app", app_name))

    if command.startswith("restart "):
        app_name = command.replace("restart ", "")
        restart_app(app_name)
        return DispatchResult(reply=generate_response("restart_app", app_name))

    if command.startswith("timer "):
        seconds = try_parse_int(command.replace("timer ", ""))
        if seconds is None:
            return DispatchResult(reply="Please enter a valid number 🌸")
        return DispatchResult(reply=set_timer(seconds))

    if command == "cancel timer":
        return DispatchResult(reply=cancel_timer())


    if command == "tell time":
        return DispatchResult(reply=tell_time())
    if command == "tell date":
        return DispatchResult(reply=tell_date())
    if command == "battery":
        return DispatchResult(reply=battery_status())
    if command == "disk usage":
        return DispatchResult(reply=disk_usage())

    if command.startswith("calculate "):
        return DispatchResult(reply=calculate(command.replace("calculate ", "")))

    

    if command.startswith("countdown "):
        seconds = try_parse_int(command.replace("countdown ", ""))
        if seconds is None:
            return DispatchResult(reply="Please enter a valid number 🌸")
        if output_var is not None and output_label is not None and app is not None:
            threading.Thread(
                target=voiced_countdown,
                args=(seconds, output_var, output_label, app),
                daemon=True,
            ).start()
        return DispatchResult()

    if command in ["hello", "hi"]:
        return DispatchResult(reply=random.choice([
            "Hello! 🌸", "Hi there! 🎀", "Welcome back! 🌷", "Hina is listening ✨"
        ]))

    if command == "how are you":
        return DispatchResult(reply=random.choice([
            "I'm doing great 🌸", "Feeling cheerful as always 🎀", "All systems happy ✨"
        ]))

    if command == "who are you":
        return DispatchResult(reply=random.choice([
            "I'm Hina, your desktop assistant 🌸",
            "Project Hina at your service 🎀",
            "Your cheerful anime companion ✨"
        ]))

    if command == "thanks":
        return DispatchResult(reply=random.choice([
            "You're welcome 🌸", "Happy to help 🎀", "Anytime ✨"
        ]))

    if command == "what can you do":
        return DispatchResult(reply="Open apps, manage files, tell time, calculate, set timers, and more 🌸")

    return DispatchResult(reply=random.choice([
        "Hmm, I don't know that one yet 🌸",
        "Hina is still learning! 🎀",
        "That's a new one for me ✨"
    ]))
