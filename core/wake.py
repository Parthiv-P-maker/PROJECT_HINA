"""
Wake word, "Hey Jarvis" by default (roadmap 2.2). The phrase is a setting
("wake_phrase": "jarvis" or "hina"); see WAKE_PHRASES.

Detection is two stages built on what Hina already ships (no trained wake-word
model needed):

  1. Silero VAD (core/stt.StreamingVad) listens continuously and cuts out short
     stretches of speech. This is cheap: a tiny ONNX model per 32 ms of audio.
  2. Only those stretches go to Whisper, and match_wake() checks whether they
     start with the wake phrase.

So Whisper runs only when someone actually speaks, never on silence. A trained
wake-word model could later replace stage 2 behind the same `on_wake` callback.

When the wake phrase is followed by a command in the same breath ("Hey Jarvis,
open Chrome"), that stretch is transcribed again with the usual command prompt
and the command is passed on directly; otherwise the window opens the mic.

Every check is logged ("Wake check heard ..."), so a phrase that doesn't wake
Hina can be traced to what Whisper actually wrote.
"""

import re
import threading
import time

from core import stt
from utils.logger import get_logger

logger = get_logger(__name__)

# For each phrase: what Whisper writes for the name (counts at the very start of what was said),
# extra spellings that only count after "hey"/"hi"/... (alone they're too likely to be real words),
# and a prompt that steers Whisper's spelling without containing the wake phrase itself
# (on unclear audio Whisper tends to repeat its prompt, and that must not wake Hina).
WAKE_PHRASES = {
    "jarvis": {
        "label": "Hey Jarvis",
        "names": {"jarvis", "jarvis's", "jarviss", "jarves", "jervis", "jarvus", "jarvas", "jarvys"},
        "after_greeting": {"javis", "travis", "jarbis", "darvis", "garvis"},
        "prompt": "Names: Jarvis, Maya, Arjun.",
    },
    "hina": {
        "label": "Hey Hina",
        "names": {"hina", "heena", "hinna", "hena", "hinah", "heina", "hyna", "haina", "hiena", "heenah", "hīna"},
        "after_greeting": {"nina", "ina", "ena", "hyena", "henna", "hannah", "hanna", "hina's"},
        "prompt": "Names: Hina, Maya, Arjun.",
    },
}
DEFAULT_PHRASE = "jarvis"
GREETINGS = {"hey", "hi", "hay", "ok", "okay", "oh", "yo", "hello", "a", "ay", "eh"}
WAKE_PROMPT = WAKE_PHRASES[DEFAULT_PHRASE]["prompt"]


def phrase_key(name):
    """A known phrase key ("jarvis"/"hina") for a setting value or label; the default otherwise."""
    key = (name or "").strip().lower().replace("hey ", "")
    return key if key in WAKE_PHRASES else DEFAULT_PHRASE


def label(name=None):
    return WAKE_PHRASES[phrase_key(name)]["label"]

SEGMENT_END_BLOCKS = 4      # 0.4 s of quiet ends a stretch of speech
SEGMENT_MAX_BLOCKS = 60     # 6 s: room for "Hey Hina, open Spotify and set a timer"
SEGMENT_MIN_BLOCKS = 3      # shorter blips (a cough, a click) are ignored
PRE_ROLL_BLOCKS = 3

_WORD = re.compile(r"[a-zāīū']+", re.IGNORECASE)


def _words(text):
    """[(lowercase word, end offset)], with spelled-out letters joined: "J.A.R.V.I.S." -> "jarvis"."""
    out = []
    for m in _WORD.finditer(text or ""):
        word = m.group(0).lower()
        if len(word) == 1 and out and out[-1][2]:  # extend a run of single letters
            prev = out.pop()
            out.append((prev[0] + word, m.end(), True))
        else:
            out.append((word, m.end(), len(word) == 1))
    return [(w, end) for w, end, _ in out]


def match_wake(text, phrase=DEFAULT_PHRASE):
    """(woke, the rest of what was said) for one transcribed stretch of speech."""
    spec = WAKE_PHRASES[phrase_key(phrase)]
    names, after = spec["names"], spec["names"] | spec["after_greeting"]
    words = _words(text)
    if not words:
        return False, ""
    end = None
    if words[0][0] in names:
        end = words[0][1]
    elif len(words) > 1 and words[0][0] in GREETINGS and words[1][0] in after:
        end = words[1][1]
    elif len(words) > 2 and words[0][0] in GREETINGS and words[1][0] in GREETINGS \
            and words[2][0] in after:  # "oh hey Jarvis"
        end = words[2][1]
    if end is None:
        return False, ""
    rest = text[end:].strip(" ,.!?;:-")
    return True, stt.clean_transcript(rest)


class SpeechSegmenter:
    """Feeds 0.1 s blocks; returns the blocks of a finished stretch of speech, else None."""

    def __init__(self, speech_prob):
        self.speech_prob = speech_prob
        self.reset()

    def reset(self):
        self.pre_roll, self.kept, self.quiet, self.active = [], [], 0, False

    def feed(self, block):
        prob = self.speech_prob(block)
        if not self.active:
            self.pre_roll = (self.pre_roll + [block])[-PRE_ROLL_BLOCKS:]
            if prob >= stt.VAD_START:
                self.active, self.kept = True, list(self.pre_roll)
            return None
        self.kept.append(block)
        self.quiet = self.quiet + 1 if prob < stt.VAD_END else 0
        if self.quiet >= SEGMENT_END_BLOCKS or len(self.kept) >= SEGMENT_MAX_BLOCKS:
            spoken = len(self.kept) - self.quiet
            out = self.kept if spoken >= SEGMENT_MIN_BLOCKS else None
            self.reset()
            return out
        return None


class WakeListener:
    """
    Background listener. `on_wake(command)` is called from the listener's thread
    with what followed the wake phrase ("" if nothing did).

    is_paused() -> True closes the mic (while Hina speaks, while the command mic
    is open, or while a command runs) so the two never fight over the device and
    Hina never wakes herself up.
    """

    def __init__(self, on_wake, transcriber, is_paused=lambda: False, open_blocks=None, vad=None,
                 phrase=DEFAULT_PHRASE, on_error=None):
        self.on_wake = on_wake
        self.on_error = on_error or (lambda message: None)
        self.phrase = phrase_key(phrase)
        self.transcriber = transcriber
        self.is_paused = is_paused
        self.open_blocks = open_blocks or _mic_blocks
        self.vad = vad
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hina-wake", daemon=True)
        self._thread.start()
        logger.info("Wake word listener started")

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        logger.info("Wake word listener stopped")

    def _should_listen(self):
        return not self._stop.is_set() and not self.is_paused()

    def _loop(self):
        failures = 0
        while not self._stop.is_set():
            if self.is_paused():
                time.sleep(0.1)
                continue
            try:
                self._listen_once()
                failures = 0
            except Exception as exc:  # mic unplugged, device busy...: back off and retry
                failures += 1
                logger.warning("Wake word listener error (%d): %s", failures, exc)
                if failures == 1:  # tell the user once, not on every retry
                    self.on_error(f"The wake word can't use the microphone ({exc}). Retrying in the background.")
                self._stop.wait(min(30, 2 * failures))

    def _listen_once(self):
        """Hold the mic open until paused or stopped, checking each stretch of speech."""
        vad = self.vad or stt.load_vad()
        if vad is None:
            raise RuntimeError("voice activity detection is unavailable")
        if hasattr(vad, "reset"):
            vad.reset()
        segmenter = SpeechSegmenter(vad)
        for block in self.open_blocks(self._should_listen):
            segment = segmenter.feed(block)
            if segment is not None:
                self._check(segment)

    def _check(self, blocks):
        import numpy as np
        audio = stt.normalise(np.concatenate(blocks))
        try:
            heard = self.transcriber(audio, prompt=WAKE_PHRASES[self.phrase]["prompt"]) or ""
        except Exception as exc:
            logger.warning("Wake word transcription failed: %s", exc)
            self.on_error(f"The wake word check failed ({exc}).")
            return
        woke, command = match_wake(heard, self.phrase)
        logger.info("Wake check heard %r -> %s", heard, "WAKE" if woke else "no match")
        if not woke:
            return
        if command:
            # The wake prompt is tuned for the name, not for commands: transcribe again with the
            # normal command vocabulary ("open Chrome", not "OpenCrow") and take what follows the name.
            try:
                again = self.transcriber(audio) or ""
                woke_again, better = match_wake(again, self.phrase)
                if woke_again and better:
                    logger.info("Command re-heard as %r", again)
                    command = better
            except Exception as exc:
                logger.warning("Re-transcribing the command failed: %s", exc)
        self.on_wake(command)


def _mic_blocks(keep_going):
    """0.1 s blocks of 16 kHz mono audio from the default (or HINA_MIC_DEVICE) mic while keep_going()."""
    import sounddevice as sd
    block = int(stt.SAMPLE_RATE * stt.BLOCK_SECONDS)
    with sd.InputStream(device=stt._resolve_device(sd), samplerate=stt.SAMPLE_RATE, channels=1,
                        dtype="float32", blocksize=block) as stream:
        while keep_going():
            yield stream.read(block)[0][:, 0].copy()


# ---- switching it on and off by voice ------------------------------------------
# The HUD registers a controller (it owns the mic and the settings); tools call request().
_controller = None


def set_controller(fn):
    """fn(on: bool) turns the wake word on or off in the running window (None to unregister)."""
    global _controller
    _controller = fn


def request(on):
    """Ask the running window to turn the wake word on/off. False if no window can (classic window, tests)."""
    if _controller is None:
        return False
    _controller(bool(on))
    return True
