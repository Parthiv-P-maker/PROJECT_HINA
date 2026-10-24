"""Time, date, battery, disk, calculator, timers."""

import threading

import actions
from core.countdown import voiced_countdown
from tools.registry import DispatchResult, Param, tool
from utils.helpers import try_parse_int

_INVALID_NUMBER = "Please enter a valid number 🌸"


@tool("tell_time", "Tell the user the current time.", command="tell time",
      exact_triggers=("time", "tell time"), ai=True, priority=20)
def tell_time():
    return actions.tell_time()


@tool("tell_date", "Tell the user today's date.", command="tell date",
      exact_triggers=("date", "tell date"), ai=True, priority=20)
def tell_date():
    return actions.tell_date()


@tool("battery_status", "Report the laptop's current battery percentage and charging state.",
      command="battery", exact_triggers=("battery",), ai=True, priority=20)
def battery_status():
    return actions.battery_status()


@tool("disk_usage", "Report free and total disk space.", command="disk usage",
      exact_triggers=("disk usage",), ai=True, priority=20)
def disk_usage():
    return actions.disk_usage()


@tool("calculate", "Evaluate a math expression and return the result.",
      {"expression": Param("A math expression, e.g. '25*12' or '(4+3)/2'")},
      command="calculate ", starts=("calculate ",), ai=True, priority=20)
def calculate(ctx):
    return actions.calculate(ctx.arg)


@tool("set_timer", "Start a countdown timer for a number of seconds.",
      {"seconds": Param("Duration in seconds", type="integer")},
      command="timer ", ai=True)
def set_timer(ctx):
    seconds = try_parse_int(ctx.arg)
    if seconds is None:
        return _INVALID_NUMBER
    return actions.set_timer(seconds)


@tool("cancel_timer", "Cancel the currently running timer, if any.",
      command="cancel timer", ai=True)
def cancel_timer():
    return actions.cancel_timer()


@tool("countdown", "Start a spoken countdown that shows in the window.",
      {"seconds": Param("Duration in seconds", type="integer")},
      command="countdown ")
def countdown(ctx):
    seconds = try_parse_int(ctx.arg)
    if seconds is None:
        return _INVALID_NUMBER
    if ctx.output_var is not None and ctx.output_label is not None and ctx.app is not None:
        threading.Thread(
            target=voiced_countdown,
            args=(seconds, ctx.output_var, ctx.output_label, ctx.app),
            daemon=True,
        ).start()
    return DispatchResult()
