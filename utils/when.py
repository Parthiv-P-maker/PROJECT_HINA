"""
Find a time in what the user said: "in 10 minutes", "at 6", "tomorrow at 9:30am",
"on friday at noon", "tonight".

parse_when(text, now) -> (datetime or None, the text with the time words removed)
"""

import re
from datetime import datetime, timedelta

_UNITS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600, "day": 86400}
_WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
                 "thirty": 30, "forty five": 45, "few": 3, "couple of": 2}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_RELATIVE = re.compile(
    r"\bin (?:(half an?) (hour)|(\d+(?:\.\d+)?|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) +
    r") (seconds?|secs?|minutes?|mins?|hours?|hrs?|days?))\b")
_CLOCK = re.compile(r"\b(?:at |by )?(\d{1,2})(?:[:.](\d{2}))? ?(am|pm|a\.m\.|p\.m\.)(?=\W|$)"
                    r"|\b(?:at|by) (\d{1,2})(?:[:.](\d{2}))?\b"
                    r"|\b(?:at |by )?(noon|midnight)\b")
_DAY = re.compile(r"\b(today|tonight|tomorrow)\b|\b(?:on |next |this )?(" + "|".join(_WEEKDAYS) + r")\b")
_PART = re.compile(r"\b(?:in the |this )(morning|afternoon|evening)\b")

DEFAULT_HOUR = {"morning": 9, "afternoon": 15, "evening": 19, "tonight": 20, None: 9}


def _cut(text, match):
    return (text[:match.start()] + " " + text[match.end():]) if match else text


def _hour_24(hour, minute, meridiem, part, future_day):
    if meridiem:
        hour = hour % 12 + (12 if meridiem.startswith("p") else 0)
        return [(hour, minute)]
    if hour == 0 or hour > 12:
        return [(hour % 24, minute)]
    if part in ("afternoon", "evening", "tonight"):
        return [(hour % 12 + 12, minute)]
    if part == "morning":
        return [(hour % 12, minute)]
    if future_day:  # "tomorrow at 6" -> 6pm, "tomorrow at 9" -> 9am
        return [(hour + 12 if hour <= 6 else hour % 12 + (12 if hour == 12 else 0), minute)]
    return [(hour % 12, minute), (hour % 12 + 12, minute)]  # today: whichever comes next


def parse_when(text, now=None):
    now = now or datetime.now()
    original = " " + (text or "") + " "
    text = original.lower()  # match on lowercase, cut from the original so "Mom" keeps its capital

    relative = _RELATIVE.search(text)
    if relative:
        if relative.group(1):
            seconds = 1800
        else:
            amount, unit = relative.group(3), relative.group(4)
            amount = float(amount) if amount[0].isdigit() else _WORD_NUMBERS[amount]
            seconds = amount * _UNITS[unit.rstrip("s")]
        return now + timedelta(seconds=seconds), _cut(original, relative)

    day, clock, part = _DAY.search(text), _CLOCK.search(text), _PART.search(text)
    if not (day or clock or part):
        return None, text.strip()
    # cut right to left so earlier spans keep their offsets
    spans = sorted([m for m in (day, clock, part) if m], key=lambda m: -m.start())
    rest = original
    for m in spans:
        rest = _cut(rest, m)

    which = part.group(1) if part else None
    offset, target_day = 0, None
    if day:
        if day.group(1):
            offset = {"today": 0, "tonight": 0, "tomorrow": 1}[day.group(1)]
            if day.group(1) == "tonight":
                which = "tonight"
        else:
            target_day = _WEEKDAYS.index(day.group(2))
            offset = (target_day - now.weekday()) % 7 or 7
    date = (now + timedelta(days=offset)).date()

    if clock:
        if clock.group(6):
            times = [(12, 0)] if clock.group(6) == "noon" else [(0, 0)]
            if clock.group(6) == "midnight" and offset == 0:
                date = (now + timedelta(days=1)).date()
        else:
            hour = int(clock.group(1) or clock.group(4))
            minute = int(clock.group(2) or clock.group(5) or 0)
            if hour > 23 or minute > 59:
                return None, text.strip()
            times = _hour_24(hour, minute, clock.group(3), which, offset > 0)
    else:
        times = [(DEFAULT_HOUR.get(which, 9), 0)]

    candidates = [datetime.combine(date, datetime.min.time()).replace(hour=h, minute=m) for h, m in times]
    future = [c for c in candidates if c > now]
    if future:
        return min(future), rest
    if day:  # "today at 6am" when it's already 7am: nothing sensible
        return None, text.strip()
    if clock and not clock.group(6):  # both of today's 1:00s have passed: tomorrow, by the usual guess
        hour, minute = int(clock.group(1) or clock.group(4)), int(clock.group(2) or clock.group(5) or 0)
        h, m = _hour_24(hour, minute, clock.group(3), which, True)[0]
        return datetime.combine(date + timedelta(days=1), datetime.min.time()).replace(hour=h, minute=m), rest
    return min(candidates) + timedelta(days=1), rest


def describe(due, now=None):
    """'at 6:00 PM', 'tomorrow at 9:30 AM', 'on Friday at 12:00 PM', 'in 10 minutes'."""
    now = now or datetime.now()
    seconds = (due - now).total_seconds()
    if seconds < 3600:
        minutes = max(1, round(seconds / 60))
        return f"in {minutes} minute" + ("" if minutes == 1 else "s")
    clock = due.strftime("%I:%M %p").lstrip("0")
    days = (due.date() - now.date()).days
    if days == 0:
        return f"at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    if days < 7:
        return f"on {due.strftime('%A')} at {clock}"
    return f"on {due.strftime('%d %B')} at {clock}"
