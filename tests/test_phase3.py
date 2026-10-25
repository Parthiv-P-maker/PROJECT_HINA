"""Phase 3: system/media controls (3.2, 3.3), reminders (3.4), lists (3.9)."""

from datetime import datetime, timedelta

import pytest

from core import memory_store, reminders, timers
from core.command_router import route_command
from core.dispatcher import dispatch_command
from utils.when import describe, parse_when


def say(text):
    return dispatch_command(route_command(text))


# ---- 3.2 system controls ----------------------------------------------------

@pytest.mark.parametrize("text, command", [
    ("set the volume to 40", "set volume 40"), ("volume 75%", "set volume 75"),
    ("turn it up", "volume up"), ("quieter", "volume down"), ("mute", "mute"), ("unmute", "unmute"),
    ("what's the volume", "volume level"), ("set brightness to 30", "set brightness 30"),
    ("dim the screen", "brightness down"), ("brighter", "brightness up"),
    ("lock my computer", "lock computer"), ("shut down the computer", "shutdown computer"),
    ("restart the pc", "restart computer"), ("reboot", "restart computer"),
    ("put the laptop to sleep", "sleep computer"), ("cancel shutdown", "cancel shutdown"),
    ("restart chrome", "restart chrome"),  # still the app tool
])
def test_control_phrases(text, command):
    assert route_command(text) == command


def test_volume_commands(machine):
    assert "40%" in say("set the volume to 40").reply
    assert "50%" in say("louder").reply
    assert say("mute").reply and machine.device_state["muted"]
    assert "muted" in say("what's the volume").reply
    say("unmute")
    assert not machine.device_state["muted"]
    assert "0 to 100" in dispatch_command("set volume abc").reply


def test_brightness_and_device_errors(machine, monkeypatch):
    from utils import device
    assert "60%" in say("dim the screen").reply

    def no_wmi(*a):
        raise device.DeviceError("I can't control the brightness of this screen.")

    monkeypatch.setattr(device, "set_brightness", no_wmi)
    assert "can't control the brightness" in say("set brightness to 20").reply


def test_power_actions_ask_first(machine):
    reply = say("shut down the computer")
    assert reply.needs_confirmation and "shut down the computer" in reply.reply
    assert not [c for c in machine.device if c[0] == "shutdown"]
    assert "10 seconds" in say("yes").reply
    assert ("shutdown", ()) in machine.device
    assert "Staying on" in say("cancel shutdown").reply

    assert "put the computer to sleep" in say("put the laptop to sleep").reply
    say("no")
    assert not [c for c in machine.device if c[0] == "sleep"]


def test_lock_runs_without_asking(machine):
    assert say("lock the computer").reply
    assert ("lock", ()) in machine.device


# ---- 3.3 media ----------------------------------------------------------------

def test_media_keys_and_spotify(machine, monkeypatch):
    from utils import device
    say("pause the music")
    say("next song")
    say("previous track")
    assert [c[1][0] for c in machine.device if c[0] == "media"] == ["play_pause", "next", "previous"]
    assert "Nothing's playing" in say("what's playing").reply
    monkeypatch.setattr(device, "now_playing", lambda: "Daft Punk - One More Time")
    assert "Daft Punk - One More Time" in say("what song is this").reply
    assert "lofi beats" in say("play lofi beats on spotify").reply
    assert ("spotify_search", ("lofi beats",)) in machine.device


# ---- 3.4 reminders ------------------------------------------------------------

NOW = datetime(2026, 10, 25, 14, 0)  # a Sunday afternoon


@pytest.mark.parametrize("text, due, rest", [
    ("at 6 to call mom", datetime(2026, 10, 25, 18, 0), "to call mom"),
    ("at 6pm to call mom", datetime(2026, 10, 25, 18, 0), "to call mom"),
    ("in 10 minutes to stretch", datetime(2026, 10, 25, 14, 10), "to stretch"),
    ("to drink water in an hour", datetime(2026, 10, 25, 15, 0), "to drink water"),
    ("in half an hour tea", datetime(2026, 10, 25, 14, 30), "tea"),
    ("tomorrow at 9:30am submit", datetime(2026, 10, 26, 9, 30), "submit"),
    ("tomorrow at 6 gym", datetime(2026, 10, 26, 18, 0), "gym"),
    ("on friday at noon lunch", datetime(2026, 10, 30, 12, 0), "lunch"),
    ("tonight read", datetime(2026, 10, 25, 20, 0), "read"),
    ("at 18:30 dinner", datetime(2026, 10, 25, 18, 30), "dinner"),
    ("at 1 eat", datetime(2026, 10, 26, 13, 0), "eat"),  # both of today's 1:00s are gone
    ("at 6 in the morning run", datetime(2026, 10, 26, 6, 0), "run"),
    ("at 6 to call Mom", datetime(2026, 10, 25, 18, 0), "to call Mom"),  # keeps capitals
])
def test_parse_when(text, due, rest):
    got, left = parse_when(text, NOW)
    assert got == due
    assert " ".join(left.split()) == rest


def test_parse_when_without_a_time():
    assert parse_when("to buy milk", NOW)[0] is None


def test_describe():
    assert describe(NOW + timedelta(minutes=10), NOW) == "in 10 minutes"
    assert describe(datetime(2026, 10, 26, 9, 0), NOW) == "tomorrow at 9:00 AM"


def test_set_list_and_cancel_reminders():
    assert "to call Mom" in say("remind me in 2 hours to call Mom").reply
    assert "When should I" in say("remind me to buy milk").reply
    assert "to submit the form" in say("set a reminder for tomorrow at 9 to submit the form").reply
    listed = say("what are my reminders").reply
    assert "call Mom" in listed and "submit the form" in listed
    assert "Cancelled the reminder: call Mom" in say("cancel reminder about mom").reply
    assert "Cancelled the reminder: submit the form" in say("cancel all reminders").reply
    assert "No reminders" in say("list reminders").reply


def test_due_reminders_are_announced_once_and_missed_ones_say_so():
    heard = []
    timers.set_notifier(heard.append)
    try:
        now = datetime.now()
        reminders.add(now - timedelta(hours=3), "take the bins out")
        reminders.add(now - timedelta(seconds=5), "stretch")
        reminders.add(now + timedelta(hours=1), "later")
        reminders.check(now)
        reminders.check(now)
        assert len(heard) == 2
        assert heard[0].startswith("Missed reminder") and "bins" in heard[0]
        assert heard[1] == "Reminder: stretch 🔔"
        assert [r[2] for r in reminders.pending()] == ["later"]
    finally:
        timers.set_notifier(None)


def test_reminders_are_stored_in_the_database():
    reminders.add(datetime.now() + timedelta(days=1), "dentist")
    assert [r["text"] for r in memory_store.pending_reminders()] == ["dentist"]


# ---- 3.9 lists -------------------------------------------------------------------

def test_lists_end_to_end():
    assert "milk, eggs and bread" in say("add milk, eggs and bread to my shopping list").reply
    assert "already" in say("add milk to my shopping list").reply
    assert "to-do" in say("add call the bank to my list").reply
    assert say("what's on my shopping list").reply == "On your shopping list: milk, eggs and bread 📝"
    assert "Took eggs off" in say("remove eggs from my shopping list").reply
    assert "couldn't find" in say("cross off cheese from my shopping list").reply
    assert "call the bank" in say("what's on my to do list").reply
    assert "shopping (2)" in say("what lists do i have").reply


def test_clearing_a_list_asks_first():
    say("add milk to my shopping list")
    reply = say("clear my shopping list")
    assert reply.needs_confirmation
    say("no")
    assert memory_store.list_items("shopping")
    say("clear my shopping list")
    assert "Cleared" in say("yes").reply
    assert not memory_store.list_items("shopping")


def test_list_names_are_normalised():
    from tools.planner import list_name
    assert list_name("to do") == list_name("todo") == list_name("") == "to-do"
    assert list_name("Shopping") == "shopping"
