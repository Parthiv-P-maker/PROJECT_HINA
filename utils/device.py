"""
Windows system and media controls: volume, brightness, lock/sleep/shutdown,
media keys and what Spotify is playing.

Every function here touches the real machine, so tools call them through this
module (`device.set_volume(...)`) and tests patch them. Failures raise
DeviceError with a message that is safe to show the user.
"""

import ctypes
import os
import subprocess
from urllib.parse import quote

from utils.logger import get_logger

logger = get_logger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class DeviceError(Exception):
    """str(exc) is safe to show to the user."""


# =========================
# VOLUME (Windows Core Audio through comtypes; media keys as a fallback)
# =========================

_audio_types = {}


def _audio_interfaces():
    """IMMDeviceEnumerator / IMMDevice / IAudioEndpointVolume, defined once (what pycaw wraps)."""
    if _audio_types:
        return _audio_types
    from ctypes import POINTER, c_float, c_uint, c_void_p
    from ctypes.wintypes import BOOL, DWORD
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    class IAudioEndpointVolume(IUnknown):
        _iid_ = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
        _methods_ = [
            COMMETHOD([], HRESULT, "RegisterControlChangeNotify", (["in"], c_void_p, "p")),
            COMMETHOD([], HRESULT, "UnregisterControlChangeNotify", (["in"], c_void_p, "p")),
            COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(c_uint), "count")),
            COMMETHOD([], HRESULT, "SetMasterVolumeLevel",
                      (["in"], c_float, "db"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "SetMasterVolumeLevelScalar",
                      (["in"], c_float, "level"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetMasterVolumeLevel", (["out"], POINTER(c_float), "db")),
            COMMETHOD([], HRESULT, "GetMasterVolumeLevelScalar", (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "SetChannelVolumeLevel",
                      (["in"], c_uint, "ch"), (["in"], c_float, "db"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "SetChannelVolumeLevelScalar",
                      (["in"], c_uint, "ch"), (["in"], c_float, "level"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetChannelVolumeLevel",
                      (["in"], c_uint, "ch"), (["out"], POINTER(c_float), "db")),
            COMMETHOD([], HRESULT, "GetChannelVolumeLevelScalar",
                      (["in"], c_uint, "ch"), (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "SetMute", (["in"], BOOL, "mute"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetMute", (["out"], POINTER(BOOL), "mute")),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"), (["in"], DWORD, "ctx"),
                      (["in"], c_void_p, "params"), (["out"], POINTER(POINTER(IUnknown)), "out")),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints",
                      (["in"], DWORD, "flow"), (["in"], DWORD, "mask"), (["out"], POINTER(c_void_p), "out")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], DWORD, "flow"),
                      (["in"], DWORD, "role"), (["out"], POINTER(POINTER(IMMDevice)), "out")),
        ]

    _audio_types.update(enumerator=IMMDeviceEnumerator, volume=IAudioEndpointVolume,
                        clsid=GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"))
    return _audio_types


def _endpoint_volume():
    """IAudioEndpointVolume for the default speakers."""
    import comtypes
    types = _audio_interfaces()
    comtypes.CoInitialize()  # per thread; harmless if this thread already did it
    enumerator = comtypes.CoCreateInstance(types["clsid"], types["enumerator"], comtypes.CLSCTX_INPROC_SERVER)
    speakers = enumerator.GetDefaultAudioEndpoint(0, 1)  # eRender, eMultimedia
    unknown = speakers.Activate(types["volume"]._iid_, comtypes.CLSCTX_ALL, None)
    return unknown.QueryInterface(types["volume"])


def _media_key(name):
    try:
        import keyboard
        keyboard.send(name)
    except Exception as exc:
        logger.warning("Media key %r failed: %s", name, exc)
        raise DeviceError("I couldn't press that media key.") from exc


def get_volume():
    """(percent 0-100, muted)."""
    try:
        endpoint = _endpoint_volume()
        return round(endpoint.GetMasterVolumeLevelScalar() * 100), bool(endpoint.GetMute())
    except Exception as exc:
        logger.warning("Reading the volume failed: %s", exc)
        raise DeviceError("I can't read the volume on this machine.") from exc


def set_volume(percent):
    """Set the master volume (0-100); anything above 0 also unmutes. Returns the new percent."""
    percent = max(0, min(100, int(percent)))
    try:
        endpoint = _endpoint_volume()
        endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
        if percent:
            endpoint.SetMute(False, None)
        return percent
    except Exception as exc:
        logger.warning("Core Audio failed, using volume keys: %s", exc)
    for _ in range(50):           # each key press is 2%: go to 0, then up
        _media_key("volume down")
    for _ in range(percent // 2):
        _media_key("volume up")
    return percent


def change_volume(delta):
    """Raise/lower the volume by `delta` percent. Returns the new percent, or None if unknown."""
    try:
        current, _ = get_volume()
    except DeviceError:
        for _ in range(max(1, abs(delta) // 2)):
            _media_key("volume up" if delta > 0 else "volume down")
        return None
    return set_volume(current + delta)


def set_mute(muted):
    try:
        _endpoint_volume().SetMute(bool(muted), None)
    except Exception as exc:
        logger.warning("Core Audio mute failed, using the mute key: %s", exc)
        _media_key("volume mute")  # a toggle: the best we can do without Core Audio


# =========================
# BRIGHTNESS (laptop panels, through WMI)
# =========================

_NO_BRIGHTNESS = "I can't control the brightness of this screen (external monitors usually don't allow it)."


def _powershell(script, timeout=10):
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise DeviceError((result.stderr or "PowerShell failed").strip().splitlines()[0])
    return (result.stdout or "").strip()


def get_brightness():
    try:
        return int(_powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness"
                               " | Select-Object -First 1).CurrentBrightness"))
    except Exception as exc:
        logger.warning("Reading brightness failed: %s", exc)
        raise DeviceError(_NO_BRIGHTNESS) from exc


def set_brightness(percent):
    percent = max(0, min(100, int(percent)))
    try:
        _powershell("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                    "Invoke-CimMethod -MethodName WmiSetBrightness "
                    f"-Arguments @{{Timeout=1; Brightness={percent}}} | Out-Null")
        return percent
    except Exception as exc:
        logger.warning("Setting brightness failed: %s", exc)
        raise DeviceError(_NO_BRIGHTNESS) from exc


# =========================
# POWER
# =========================

def lock():
    if not ctypes.windll.user32.LockWorkStation():
        raise DeviceError("Windows wouldn't lock just now.")


def sleep():
    # SetSuspendState(hibernate=0, force=1, wake events=0); hibernates instead if hibernation is on
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=_NO_WINDOW)


SHUTDOWN_DELAY = 10


def shutdown(restart=False, delay=SHUTDOWN_DELAY):
    """Shut down (or restart) after `delay` seconds; cancel_shutdown() in that window stops it."""
    subprocess.Popen(["shutdown", "/r" if restart else "/s", "/t", str(delay)], creationflags=_NO_WINDOW)


def cancel_shutdown():
    result = subprocess.run(["shutdown", "/a"], capture_output=True, text=True, creationflags=_NO_WINDOW)
    return result.returncode == 0


# =========================
# MEDIA
# =========================

MEDIA_KEYS = {"play_pause": "play/pause media", "next": "next track", "previous": "previous track"}


def media(action):
    _media_key(MEDIA_KEYS[action])


def now_playing():
    """'Artist - Song' from Spotify's window title; '' if it's paused or not open."""
    try:
        import psutil
        import win32gui
        import win32process
    except Exception as exc:
        raise DeviceError("I can't see other windows on this machine.") from exc

    spotify = {p.pid for p in psutil.process_iter(["name"])
               if (p.info["name"] or "").lower() == "spotify.exe"}
    titles = []

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in spotify:
                titles.append(win32gui.GetWindowText(hwnd))
        return True

    if spotify:
        win32gui.EnumWindows(visit, None)
    for title in titles:
        # paused / idle titles are just "Spotify" or "Spotify Premium"
        if " - " in title and not title.lower().startswith("spotify"):
            return title
    return ""


def spotify_search(query):
    os.startfile("spotify:search:" + quote(query))
