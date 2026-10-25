"""
Speech-to-text for Hina (push-to-talk).

Mic capture and the transcription model are injected, so everything here can be
unit-tested without a microphone. The defaults are:

  * recorder     - sounddevice, 16 kHz mono, stops itself after a pause
                   (Silero VAD decides what is speech; plain loudness if it can't load)
  * transcriber  - faster-whisper (offline, CPU, int8; model is downloaded once)

Both heavy imports are lazy: importing this module costs nothing, and a missing
mic / package / model turns into a friendly SttError, never a crash.
"""

import os
import re
import threading
import time

from utils.logger import get_logger

logger = get_logger(__name__)

SAMPLE_RATE = 16000
# HINA_STT_MODEL forces a model; otherwise small.en on an NVIDIA GPU, base.en on CPU.
MODEL_NAME = os.environ.get("HINA_STT_MODEL") or None
GPU_MODEL, CPU_MODEL = "small.en", "base.en"

# Whisper guesses spellings from context; priming it with Hina's own command
# words turned "Open Croak" into "Open Chrome" in testing, at no speed cost.
COMMAND_PROMPT = ("Commands for Hina: tell time, tell date, open chrome, close notepad, "
                  "calculate 25 times 12, find file, find folder, open file, set name, "
                  "search google, search chatgpt, timer 5 minutes, countdown, cancel timer, "
                  "mode focus, battery, disk usage, favorite app.")
# No "bye" in the prompt: on unclear audio Whisper tends to output the prompt's
# last words, and "bye" shuts Hina down.

MAX_RECORD_SECONDS = 12.0
NO_SPEECH_TIMEOUT = 6.0     # give up if nobody says anything
END_SILENCE_SECONDS = 0.9   # pause that ends the phrase
BLOCK_SECONDS = 0.1
PRE_ROLL_BLOCKS = 3         # keep 0.3s before speech starts so the first word isn't clipped
NOISE_FACTOR = 4.0          # speech = this many times louder than the room
MIN_THRESHOLD = 0.001       # RMS floor; laptop mic arrays can be very quiet
DEAD_MIC_LEVEL = 0.0005     # nothing louder than this in a whole attempt = silent input
SPEAKING_WAIT_SECONDS = 15.0  # how long to wait for Hina to finish talking

# Silero VAD (the copy bundled with faster-whisper): speech probability per 32 ms.
VAD_START = 0.5             # speech starts when a block scores at least this
VAD_END = 0.35              # and counts as a pause below this
VAD_END_SILENCE_SECONDS = 0.7  # VAD is sure about pauses, so it can stop sooner than loudness

# HINA_MIC_DEVICE picks the input: a device index or part of its name ("Realtek").
MIC_DEVICE = os.environ.get("HINA_MIC_DEVICE") or None


class SttError(Exception):
    """Something went wrong; str(exc) is safe to show to the user."""


def _rms(block):
    total = 0.0
    for sample in block:
        total += float(sample) * float(sample)
    return (total / len(block)) ** 0.5 if len(block) else 0.0


def collect_phrase(read_block, cancel=None, rms=_rms, speech_prob=None, no_speech_timeout=None):
    """
    Pull fixed-size blocks from read_block() and keep the spoken phrase.

    With speech_prob(block) -> 0..1 (voice activity detection) a block is speech
    when the model says so; without it, when it is clearly louder than the room.
    `no_speech_timeout` (seconds) overrides how long to wait for the first word
    (follow-up listening waits longer than push-to-talk).

    Returns the list of kept blocks, or None if cancelled / nothing was said.
    Raises SttError when the input was silent the whole time (muted mic,
    zero input gain, wrong device), which is different from "you said nothing".
    """
    max_blocks = int(MAX_RECORD_SECONDS / BLOCK_SECONDS)
    no_speech_blocks = int((no_speech_timeout or NO_SPEECH_TIMEOUT) / BLOCK_SECONDS)
    end_blocks = int((VAD_END_SILENCE_SECONDS if speech_prob else END_SILENCE_SECONDS) / BLOCK_SECONDS)

    pre_roll, kept, noise = [], [], []
    started, quiet, loudest = False, 0, 0.0
    threshold = MIN_THRESHOLD

    for count in range(max_blocks):
        if cancel is not None and cancel.is_set():
            return None
        block = read_block()
        level = rms(block)
        loudest = max(loudest, level)

        if len(noise) < 3:  # first 0.3s calibrates the room noise
            noise.append(level)
            threshold = max(MIN_THRESHOLD, NOISE_FACTOR * sum(noise) / len(noise))

        prob = speech_prob(block) if speech_prob else None

        if not started:
            pre_roll = (pre_roll + [block])[-PRE_ROLL_BLOCKS:]
            is_speech = prob >= VAD_START if prob is not None else (len(noise) >= 3 and level >= threshold)
            if is_speech:
                started, kept = True, list(pre_roll)
            elif count >= no_speech_blocks:
                break
            continue

        kept.append(block)
        is_pause = prob < VAD_END if prob is not None else level < threshold
        quiet = quiet + 1 if is_pause else 0
        if quiet >= end_blocks:
            break

    if not started:
        logger.info("No speech heard (loudest RMS %.5f, threshold %.5f)", loudest, threshold)
        if loudest < DEAD_MIC_LEVEL:
            raise SttError("My mic is only hearing silence 🎤 Check the input device and its "
                           "volume in Windows Sound settings (or set HINA_MIC_DEVICE).")
        return None
    return kept


class StreamingVad:
    """
    Speech probability for a live 16 kHz stream, block by block.

    Wraps the Silero model bundled with faster-whisper but keeps its recurrent
    state and audio context between blocks (faster-whisper's own wrapper resets
    them on every call, which suits whole files, not a live mic).
    """

    CHUNK = 512    # samples per model step (32 ms)
    CONTEXT = 64   # samples of the previous chunk the model also sees

    def __init__(self, session=None):
        if session is None:
            from faster_whisper.vad import get_vad_model
            session = get_vad_model().session
        self.session = session
        self.reset()

    def reset(self):
        import numpy as np
        self._h = np.zeros((1, 1, 128), dtype="float32")
        self._c = np.zeros((1, 1, 128), dtype="float32")
        self._context = np.zeros(self.CONTEXT, dtype="float32")
        self._pending = np.zeros(0, dtype="float32")

    def __call__(self, block):
        """Highest speech probability among the complete chunks in `block` (plus leftovers)."""
        import numpy as np
        audio = np.concatenate([self._pending, np.asarray(block, dtype="float32")])
        best = 0.0
        while len(audio) >= self.CHUNK:
            chunk, audio = audio[:self.CHUNK], audio[self.CHUNK:]
            frame = np.concatenate([self._context, chunk])[None, :]
            out, self._h, self._c = self.session.run(None, {"input": frame, "h": self._h, "c": self._c})
            best = max(best, float(np.asarray(out).reshape(-1)[0]))
            self._context = chunk[-self.CONTEXT:]
        self._pending = audio
        return best


_vad = {"model": None, "failed": False}


def load_vad():
    """A fresh StreamingVad, or None if it can't load (then loudness decides)."""
    if _vad["failed"]:
        return None
    try:
        if _vad["model"] is None:
            _vad["model"] = StreamingVad()
            logger.info("Voice activity detection: Silero VAD")
        _vad["model"].reset()
        return _vad["model"]
    except Exception as exc:
        _vad["failed"] = True
        logger.warning("Silero VAD unavailable, using loudness to find speech: %s", exc)
        return None


def _resolve_device(sd, wanted=MIC_DEVICE):
    if wanted is None:
        return None
    if str(wanted).isdigit():
        return int(wanted)
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0 and str(wanted).lower() in device["name"].lower():
            return index
    raise SttError(f"I can't find a microphone matching '{wanted}' (HINA_MIC_DEVICE) 🎤")


def record_until_silence(cancel=None, no_speech_timeout=None):
    """Record from the mic until the speaker pauses. Returns float32 mono samples
    normalised to a healthy level, or None if nothing was said / cancelled."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        raise SttError("Voice input needs the 'sounddevice' package 🌸") from exc

    block = int(SAMPLE_RATE * BLOCK_SECONDS)
    device = _resolve_device(sd)
    vad = load_vad()
    try:
        with sd.InputStream(device=device, samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", blocksize=block) as stream:
            kept = collect_phrase(
                lambda: stream.read(block)[0][:, 0].copy(),
                cancel,
                rms=lambda b: float(np.sqrt(np.mean(b ** 2))),
                speech_prob=vad,
                no_speech_timeout=no_speech_timeout,
            )
    except SttError:
        raise
    except Exception as exc:
        logger.warning("Microphone failed: %s", exc)
        raise SttError("I can't reach a microphone 🎤 Check it's plugged in and allowed.") from exc

    if not kept:
        return None
    return normalise(np.concatenate(kept))


def normalise(audio, target_peak=0.9):
    """Quiet mics produce audio Whisper's VAD can discard; scale it up."""
    peak = float(abs(audio).max()) if len(audio) else 0.0
    if peak <= 0.0:
        return audio
    return audio * (target_peak / peak)


def mic_test(seconds=5):
    """`python -m core.stt` - prints a live level meter so you can see what the mic hears."""
    import numpy as np
    import sounddevice as sd

    device = _resolve_device(sd)
    info = sd.query_devices(device, kind="input")
    print(f"Input: {info['name']}  (set HINA_MIC_DEVICE to change)")
    print(f"Talk now for {seconds}s...")
    block = int(SAMPLE_RATE * BLOCK_SECONDS)
    loudest = 0.0
    with sd.InputStream(device=device, samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=block) as stream:
        for _ in range(int(seconds / BLOCK_SECONDS)):
            level = float(np.sqrt(np.mean(stream.read(block)[0][:, 0] ** 2)))
            loudest = max(loudest, level)
            bar = "#" * min(60, int(level * 600))
            print(f"{level:8.5f} |{bar}")
    print(f"Loudest: {loudest:.5f}  (speech usually 0.01-0.1; under {DEAD_MIC_LEVEL} means the input is silent)")


def _looks_like_network_error(exc):
    """Walk the cause chain: huggingface_hub wraps connection/SSL/offline errors."""
    while exc is not None:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        if any(k in name for k in ("connection", "timeout", "ssl", "offline", "httperror", "localentrynotfound")):
            return True
        if any(k in text for k in ("offline", "connection", "ssl", "cannot find the requested files")):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _gpu_available():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def build_prompt():
    """Command vocabulary plus the user's saved name, so names spell correctly."""
    try:
        from memory import get_name
        name = get_name()
    except Exception:
        name = None
    return f"{COMMAND_PROMPT} My name is {name}." if name else COMMAND_PROMPT


class WhisperTranscriber:
    """faster-whisper behind a lazy, cached model load (GPU if there is one)."""

    def __init__(self, model_name=MODEL_NAME, prompt=build_prompt, use_gpu=None):
        self.model_name = model_name
        self.prompt = prompt
        self.use_gpu = _gpu_available() if use_gpu is None else use_gpu
        self._model = None
        self._lock = threading.Lock()

    def _build(self, gpu):
        import sys
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            logger.exception("faster-whisper import failed (python: %s)", sys.executable)
            raise SttError("The 'faster-whisper' package isn't installed for the Python running Hina "
                           f"({sys.executable}). Run: pip install faster-whisper") from exc

        name = self.model_name or (GPU_MODEL if gpu else CPU_MODEL)
        device, compute = ("cuda", "float16") if gpu else ("cpu", "int8")
        try:
            model = WhisperModel(name, device=device, compute_type=compute)
            logger.info("Speech model %s loaded on %s", name, device)
            return model
        except Exception as exc:
            logger.exception("Loading speech model %r on %s failed", name, device)
            if gpu:
                return None  # caller falls back to CPU
            if _looks_like_network_error(exc):
                raise SttError(f"I couldn't download my listening model '{name}' "
                               "(network/HuggingFace problem). Check your connection and try again 🌸") from exc
            raise SttError(f"My listening model failed to load ({type(exc).__name__}: {exc}) 🌸") from exc

    def _load(self):
        with self._lock:
            if self._model is None and self.use_gpu:
                self._model = self._build(gpu=True)
                if self._model is None:
                    self.use_gpu = False
            if self._model is None:
                self._model = self._build(gpu=False)
        return self._model

    def _transcribe(self, audio, prompt=None):
        if prompt is None:
            prompt = self.prompt() if callable(self.prompt) else self.prompt
        segments, _ = self._load().transcribe(
            audio, language="en", vad_filter=True, beam_size=5,
            initial_prompt=prompt, condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def __call__(self, audio, prompt=None):
        """Transcribe `audio`; `prompt` replaces the usual command-word prompt (the wake word uses its own)."""
        try:
            return self._transcribe(audio, prompt)
        except SttError:
            raise
        except Exception as exc:
            if self.use_gpu:  # e.g. CUDA libraries missing: only shows up on first use
                logger.warning("GPU transcription failed, retrying on CPU: %s", exc)
                with self._lock:
                    self.use_gpu, self._model = False, None
                return self(audio, prompt)
            logger.warning("Transcription failed: %s", exc)
            raise SttError("I couldn't make out that audio 🌸") from exc


_SPOKEN_MATH = [
    (r"\bmultiplied by\b|\btimes\b|(?<=\d)\s*x\s*(?=\d)", "*"),
    (r"\bdivided by\b|\bover\b", "/"),
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\bto the power of\b", "**"),
]


def clean_transcript(text):
    """
    Whisper writes prose ("Open Chrome.", "Calculate 25 times 12."); Hina's
    commands are terse. Drop sentence punctuation and turn spoken maths into
    symbols so voice input matches what a user would have typed.
    """
    text = (text or "").strip()
    # sentence punctuation only: keep dots inside names like notes.txt
    text = re.sub(r"[,!?;:\"]", " ", text)
    text = re.sub(r"\.(?=\s|$)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text.lower().startswith("calculate"):
        for pattern, symbol in _SPOKEN_MATH:
            text = re.sub(pattern, f" {symbol} ", text, flags=re.IGNORECASE)
        text = text.replace(",", "")
        text = re.sub(r"\s+", " ", text).strip()
    return text


class SpeechInput:
    """
    listen() -> transcribed text ("" when nothing was heard).

    recorder(cancel_event) -> audio or None; transcriber(audio) -> str;
    is_speaking() -> bool says whether Hina's own TTS is playing; on_state(name)
    is called with "waiting", "listening" and "transcribing" as they begin.
    """

    def __init__(self, recorder=None, transcriber=None, is_speaking=None, on_state=None,
                 speaking_wait=SPEAKING_WAIT_SECONDS):
        self.recorder = recorder or record_until_silence
        self.transcriber = transcriber or WhisperTranscriber()
        self.is_speaking = is_speaking or (lambda: False)
        self.on_state = on_state or (lambda state: None)
        self.speaking_wait = speaking_wait
        self.cancel = threading.Event()

    def _wait_for_silence(self):
        """Never record while Hina is talking, or she would transcribe herself."""
        end = time.time() + self.speaking_wait
        announced = False
        while self.is_speaking():
            if self.cancel.is_set():
                return
            if time.time() > end:
                raise SttError("I'm still talking - try again in a moment 🌸")
            if not announced:
                self.on_state("waiting")
                announced = True
            time.sleep(0.05)
        if announced:
            time.sleep(0.25)  # let the speaker tail off before the mic opens

    def listen(self, no_speech_timeout=None):
        """Record one phrase and transcribe it. `no_speech_timeout` (seconds) is how long to wait
        for the first word; the recorder must accept it as a keyword when it is given."""
        self.cancel.clear()
        self._wait_for_silence()
        if self.cancel.is_set():
            return ""

        self.on_state("listening")
        extra = {"no_speech_timeout": no_speech_timeout} if no_speech_timeout else {}
        audio = self.recorder(self.cancel, **extra)
        if audio is None or len(audio) == 0 or self.cancel.is_set():
            return ""

        self.on_state("transcribing")
        heard = self.transcriber(audio) or ""
        logger.info("Heard: %r", heard)
        return clean_transcript(heard)


if __name__ == "__main__":
    mic_test()
