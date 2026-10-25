"""
"Hey Hina" wake word (roadmap 2.2).

There is no ready-made "Hina" model for openWakeWord or Porcupine, so detection
is two stages built on what Hina already ships:

  1. Silero VAD (core/stt.StreamingVad) listens continuously and cuts out short
     stretches of speech. This is cheap: a tiny ONNX model per 32 ms of audio.
  2. Only those stretches go to Whisper, and match_wake() checks whether they
     start with the wake phrase.

So Whisper runs only when someone actually speaks, never on silence. A trained
wake-word model could later replace stage 2 behind the same `on_wake` callback.

When the wake phrase is followed by a command in the same breath ("Hey Hina,
open Chrome"), the command is passed on directly; otherwise the window opens
the mic for the command.
"""

import re
import threading
import time

from core import stt
from utils.logger import get_logger

logger = get_logger(__name__)

# What Whisper writes for "Hina". Bare names count only at the very start.
WAKE_NAMES = {"hina", "heena", "hinna", "hena", "hinah", "heina", "hyna", "haina", "hiena", "heenah", "hīna"}
# These only count after "hey"/"hi"/...: on their own they're too likely to be real names.
WAKE_NAMES_AFTER_GREETING = WAKE_NAMES | {"nina", "ina", "ena", "hyena", "henna"}
GREETINGS = {"hey", "hi", "hay", "ok", "okay", "oh", "yo", "hello", "a", "ay", "eh"}

# Steers Whisper toward the spelling without containing the wake phrase itself:
# on unclear audio Whisper tends to repeat its prompt, and that must not wake Hina.
WAKE_PROMPT = "Names: Hina, Maya, Arjun."

SEGMENT_END_BLOCKS = 4      # 0.4 s of quiet ends a stretch of speech
SEGMENT_MAX_BLOCKS = 60     # 6 s: room for "Hey Hina, open Spotify and set a timer"
SEGMENT_MIN_BLOCKS = 3      # shorter blips (a cough, a click) are ignored
PRE_ROLL_BLOCKS = 3

_WORD = re.compile(r"[a-zāīū']+")


def match_wake(text):
    """(woke, the rest of what was said) for one transcribed stretch of speech."""
    words = [(m.group(0), m.end()) for m in _WORD.finditer((text or "").lower())]
    if not words:
        return False, ""
    end = None
    if words[0][0] in WAKE_NAMES:
        end = words[0][1]
    elif len(words) > 1 and words[0][0] in GREETINGS and words[1][0] in WAKE_NAMES_AFTER_GREETING:
        end = words[1][1]
    elif len(words) > 2 and words[0][0] in GREETINGS and words[1][0] in GREETINGS \
            and words[2][0] in WAKE_NAMES_AFTER_GREETING:  # "oh hey Hina"
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

    def __init__(self, on_wake, transcriber, is_paused=lambda: False, open_blocks=None, vad=None):
        self.on_wake = on_wake
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
            heard = self.transcriber(audio, prompt=WAKE_PROMPT) or ""
        except Exception as exc:
            logger.warning("Wake word transcription failed: %s", exc)
            return
        woke, command = match_wake(heard)
        if woke:
            logger.info("Wake word heard: %r", heard)
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
