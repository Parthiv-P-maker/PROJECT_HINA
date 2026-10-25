"""System and media controls: volume, brightness, lock/sleep/shutdown, music (roadmap 3.2, 3.3)."""

import re

from tools.registry import CONFIRM, Param, ask_or_reply, tool
from utils import device

_FILLER = re.compile(r"\b(?:my|the|this|a|please)\b")


def _plain(text):
    """'lock my computer please' -> 'lock computer'."""
    return re.sub(r"\s+", " ", _FILLER.sub(" ", text.rstrip("?.! "))).strip()


def _phrases(command, *phrases):
    wanted = {_plain(p) for p in phrases}
    return lambda text: command if _plain(text) in wanted else None


def _checked(fn):
    """Run a device call; a DeviceError becomes the reply."""
    try:
        return fn()
    except device.DeviceError as exc:
        return f"{exc} 🌸"


def _level(arg):
    try:
        return max(0, min(100, int(arg)))
    except (TypeError, ValueError):
        return None


# =========================
# VOLUME
# =========================

STEP = 10

_SET_VOLUME = re.compile(r"^(?:set |turn |change |put )?(?:volume|sound)(?: level)? (?:to |at )?(\d{1,3})(?: ?%| percent)?$")


def _parse_set_volume(text):
    match = _SET_VOLUME.match(_plain(text))
    return f"set volume {match.group(1)}" if match else None


@tool("set_volume", "Set the speaker volume to a percentage.",
      {"level": Param("Volume from 0 to 100", type="integer")},
      command="set volume ", parse=_parse_set_volume, ai=True, priority=8)
def set_volume(ctx):
    level = _level(ctx.arg)
    if level is None:
        return "Give me a volume from 0 to 100 🌸"
    return _checked(lambda: f"Volume {ctx.run(level, lambda: device.set_volume(level))}% 🌸")


def _changed(delta):
    new = device.change_volume(delta)
    return f"Volume {new}% 🌸" if new is not None else ("Louder 🌸" if delta > 0 else "Quieter 🌸")


@tool("volume_up", "Turn the speaker volume up a step.", command="volume up",
      parse=_phrases("volume up", "volume up", "turn up volume", "turn volume up", "louder", "increase volume",
                     "raise volume", "turn it up", "volume louder", "sound up"),
      ai=True, priority=8)
def volume_up(ctx):
    return _checked(lambda: ctx.run("+%d" % STEP, lambda: _changed(STEP)))


@tool("volume_down", "Turn the speaker volume down a step.", command="volume down",
      parse=_phrases("volume down", "volume down", "turn down volume", "turn volume down", "quieter", "softer",
                     "decrease volume", "lower volume", "turn it down", "sound down"),
      ai=True, priority=8)
def volume_down(ctx):
    return _checked(lambda: ctx.run("-%d" % STEP, lambda: _changed(-STEP)))


@tool("mute", "Mute the speakers.", command="mute",
      parse=_phrases("mute", "mute", "mute sound", "mute volume", "mute audio", "mute speakers"),
      ai=True, priority=8)
def mute(ctx):
    return _checked(lambda: ctx.run("on", lambda: device.set_mute(True)) or "Muted 🌸")


@tool("unmute", "Unmute the speakers.", command="unmute",
      parse=_phrases("unmute", "unmute", "unmute sound", "unmute volume", "unmute audio", "unmute speakers"),
      ai=True, priority=8)
def unmute(ctx):
    return _checked(lambda: ctx.run("off", lambda: device.set_mute(False)) or "Unmuted 🌸")


def _volume_report():
    level, muted = device.get_volume()
    return f"Volume is {level}%" + (", but muted 🌸" if muted else " 🌸")


@tool("volume_level", "Tell the user the current volume.", command="volume level",
      parse=_phrases("volume level", "volume", "volume level", "what's volume", "whats volume",
                     "what is volume", "how loud is it"),
      ai=True, priority=8)
def volume_level():
    return _checked(_volume_report)


# =========================
# BRIGHTNESS
# =========================

_SET_BRIGHTNESS = re.compile(r"^(?:set |turn |change |put )?(?:brightness|screen brightness)(?: level)? "
                             r"(?:to |at )?(\d{1,3})(?: ?%| percent)?$")


def _parse_set_brightness(text):
    match = _SET_BRIGHTNESS.match(_plain(text))
    return f"set brightness {match.group(1)}" if match else None


@tool("set_brightness", "Set the screen brightness to a percentage.",
      {"level": Param("Brightness from 0 to 100", type="integer")},
      command="set brightness ", parse=_parse_set_brightness, ai=True, priority=8)
def set_brightness(ctx):
    level = _level(ctx.arg)
    if level is None:
        return "Give me a brightness from 0 to 100 🌸"
    return _checked(lambda: f"Brightness {ctx.run(level, lambda: device.set_brightness(level))}% 🌸")


def _nudge_brightness(delta):
    return f"Brightness {device.set_brightness(device.get_brightness() + delta)}% 🌸"


@tool("brightness_up", "Make the screen brighter.", command="brightness up",
      parse=_phrases("brightness up", "brightness up", "brighter", "increase brightness", "raise brightness",
                     "turn up brightness", "make screen brighter", "screen brighter"),
      ai=True, priority=8)
def brightness_up(ctx):
    return _checked(lambda: ctx.run("+%d" % STEP, lambda: _nudge_brightness(STEP)))


@tool("brightness_down", "Dim the screen.", command="brightness down",
      parse=_phrases("brightness down", "brightness down", "dimmer", "dim screen", "decrease brightness",
                     "lower brightness", "turn down brightness", "make screen darker", "screen darker"),
      ai=True, priority=8)
def brightness_down(ctx):
    return _checked(lambda: ctx.run("-%d" % STEP, lambda: _nudge_brightness(-STEP)))


@tool("brightness_level", "Tell the user the current screen brightness.", command="brightness level",
      parse=_phrases("brightness level", "brightness", "brightness level", "what's brightness",
                     "whats brightness", "what is brightness"),
      priority=8)
def brightness_level():
    return _checked(lambda: f"Brightness is {device.get_brightness()}% 🌸")


# =========================
# POWER
# =========================

@tool("lock_computer", "Lock the computer (the Windows lock screen).", command="lock computer",
      parse=_phrases("lock computer", "lock", "lock computer", "lock pc", "lock laptop", "lock screen",
                     "lock windows"),
      ai=True, priority=8)
def lock_computer(ctx):
    return _checked(lambda: ctx.run("computer", device.lock) or "Locking 🌸")


@tool("sleep_computer", "Put the computer to sleep.", command="sleep computer",
      parse=_phrases("sleep computer", "sleep computer", "sleep pc", "sleep laptop", "put computer to sleep",
                     "put pc to sleep", "put laptop to sleep", "computer sleep"),
      tier=CONFIRM, ai=True, priority=8)
def sleep_computer(ctx):
    return ask_or_reply(ctx.run("the computer", lambda: device.sleep() or "Going to sleep 🌙"))


_WITHIN = f"in {device.SHUTDOWN_DELAY} seconds. Say \"cancel shutdown\" to stop it"


@tool("shutdown", "Shut the computer down.", command="shutdown computer",
      parse=_phrases("shutdown computer", "shutdown", "shut down", "shutdown computer", "shut down computer",
                     "shut down pc", "shutdown pc", "turn off computer", "turn off pc", "turn off laptop",
                     "power off", "power off computer", "shut down laptop"),
      tier=CONFIRM, ai=True, priority=8)
def shutdown(ctx):
    return ask_or_reply(ctx.run("the computer", lambda: device.shutdown() or f"Shutting down {_WITHIN} 🌸"))


@tool("restart_computer", "Restart the computer.", command="restart computer",
      parse=_phrases("restart computer", "restart computer", "restart pc", "restart laptop", "reboot",
                     "reboot computer", "reboot pc", "restart windows"),
      tier=CONFIRM, ai=True, priority=8)
def restart_computer(ctx):
    return ask_or_reply(ctx.run("the computer", lambda: device.shutdown(restart=True) or f"Restarting {_WITHIN} 🌸"))


@tool("cancel_shutdown", "Cancel a shutdown or restart that hasn't happened yet.", command="cancel shutdown",
      parse=_phrases("cancel shutdown", "cancel shutdown", "abort shutdown", "stop shutdown", "dont shut down",
                     "don't shut down", "cancel restart", "abort restart", "stop restart"),
      ai=True, priority=8)
def cancel_shutdown(ctx):
    done = ctx.run("computer", device.cancel_shutdown)
    return "Cancelled. Staying on 🌸" if done else "There's no shutdown to cancel 🌸"


# =========================
# MEDIA (roadmap 3.3)
# =========================

@tool("media_play_pause", "Play or pause the music or video that's playing.", command="play pause",
      parse=_phrases("play pause", "play", "pause", "resume", "play music", "pause music", "resume music",
                     "pause song", "play pause", "stop music", "pause spotify", "play spotify",
                     "resume spotify", "unpause"),
      ai=True, priority=8)
def media_play_pause(ctx):
    return _checked(lambda: ctx.run("play/pause", lambda: device.media("play_pause")) or "Done 🎵")


@tool("media_next", "Skip to the next song.", command="next song",
      parse=_phrases("next song", "next", "next song", "next track", "skip", "skip song", "skip track",
                     "skip this song", "play next song"),
      ai=True, priority=8)
def media_next(ctx):
    return _checked(lambda: ctx.run("next", lambda: device.media("next")) or "Next song 🎵")


@tool("media_previous", "Go back to the previous song.", command="previous song",
      parse=_phrases("previous song", "previous", "previous song", "previous track", "last song",
                     "go back a song", "play previous song", "play last song"),
      ai=True, priority=8)
def media_previous(ctx):
    return _checked(lambda: ctx.run("previous", lambda: device.media("previous")) or "Previous song 🎵")


def _playing():
    title = device.now_playing()
    return f"Playing {title} 🎵" if title else "Nothing's playing on Spotify right now 🎵"


@tool("now_playing", "Tell the user which song is playing on Spotify.", command="whats playing",
      parse=_phrases("whats playing", "what's playing", "whats playing", "what is playing",
                     "what song is this", "what song is playing", "whats this song", "what's this song",
                     "which song is this", "name this song"),
      ai=True, priority=8)
def now_playing():
    return _checked(_playing)


_SPOTIFY = re.compile(r"^(?:play|search for|search|find|put on) (.+?) on spotify$|^search spotify for (.+)$")


def _parse_spotify(text):
    match = _SPOTIFY.match(text.rstrip("?.! "))
    if not match:
        return None
    return "spotify " + (match.group(1) or match.group(2)).strip()


@tool("spotify_search", "Search Spotify for a song, artist, album or playlist.",
      {"query": Param("What to look for, e.g. 'lofi beats' or 'Taylor Swift'")},
      command="spotify ", parse=_parse_spotify, ai=True, priority=8)
def spotify_search(ctx):
    query = ctx.arg.strip()
    if not query:
        return "What should I look for on Spotify? 🎵"
    try:
        ctx.run(query, lambda: device.spotify_search(query))
    except OSError:
        return "I couldn't open Spotify. Is it installed? 🎵"
    return f"Searching Spotify for {query} 🎵"
