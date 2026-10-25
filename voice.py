"""
Hina's voice. One speaker thread speaks queued sentences in order, trying:

  1. the neural voice (edge-tts, online), synthesised into memory and played by pygame;
     after a failure it is skipped for a few minutes instead of on every sentence;
  2. the offline neural voice (Piper), if piper-tts and a voice model are installed;
  3. the robotic Windows voice (pyttsx3).

"Local only" in settings skips 1. stop() cuts off whatever is playing (barge-in).
"""

import asyncio
import io
import os
import queue
import threading
import time
import wave

from utils.helpers import clean_text
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except Exception:
    edge_tts = None
    _HAS_EDGE_TTS = False

try:
    import pygame
    try:
        pygame.mixer.init()
        _HAS_PYGAME = True
    except Exception:
        _HAS_PYGAME = False
except Exception:
    pygame = None
    _HAS_PYGAME = False

VOICE = "en-US-AriaNeural"

# Text mostly in another script is read by a native neural voice (edge-tts) instead of the
# English one, e.g. a translation into Hindi or Malayalam. (first code point, last, voice)
SCRIPT_VOICES = [
    (0x0900, 0x097F, "hi-IN-SwaraNeural"),      # Devanagari
    (0x0980, 0x09FF, "bn-IN-TanishaaNeural"),   # Bengali
    (0x0B80, 0x0BFF, "ta-IN-PallaviNeural"),    # Tamil
    (0x0C00, 0x0C7F, "te-IN-ShrutiNeural"),     # Telugu
    (0x0C80, 0x0CFF, "kn-IN-SapnaNeural"),      # Kannada
    (0x0D00, 0x0D7F, "ml-IN-SobhanaNeural"),    # Malayalam
    (0x0600, 0x06FF, "ar-SA-ZariyahNeural"),    # Arabic
    (0x0400, 0x04FF, "ru-RU-SvetlanaNeural"),   # Cyrillic
    (0x0370, 0x03FF, "el-GR-AthinaNeural"),     # Greek
    (0x0E00, 0x0E7F, "th-TH-PremwadeeNeural"),  # Thai
    (0x3040, 0x30FF, "ja-JP-NanamiNeural"),     # Hiragana and Katakana
    (0xAC00, 0xD7AF, "ko-KR-SunHiNeural"),      # Hangul
    (0x4E00, 0x9FFF, "zh-CN-XiaoxiaoNeural"),   # Han (Japanese if any kana is present)
]
SCRIPT_SHARE = 0.3  # this share of the letters in one script switches the voice


def voice_for(text, default=None):
    """The edge-tts voice for `text`: the user's voice, unless most of it is in another script."""
    default = default or VOICE
    counts, letters = {}, 0
    for ch in text or "":
        if not ch.isalpha():
            continue
        letters += 1
        code = ord(ch)
        for low, high, name in SCRIPT_VOICES:
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break
    if not counts:
        return default
    name, n = max(counts.items(), key=lambda kv: kv[1])
    if name == "zh-CN-XiaoxiaoNeural" and counts.get("ja-JP-NanamiNeural"):
        name, n = "ja-JP-NanamiNeural", n + counts["ja-JP-NanamiNeural"]
    return name if n / max(1, letters) >= SCRIPT_SHARE else default

_speaking = 0
_speaking_lock = threading.Lock()

# One speaker thread drains this queue, so utterances never overlap or fight
# over the audio device. Items are (text, done_event_or_None, generation).
_queue = queue.Queue()
_worker = None
_worker_lock = threading.Lock()

# Barge-in: stop() bumps the generation; anything queued or playing from an
# older generation is dropped or cut off.
_generation = 0
_tts_engine = None  # the pyttsx3 engine while it is talking, so stop() can halt it


def stop():
    """Stop talking now: cut off the current sentence and drop everything queued."""
    global _generation
    _generation += 1
    if _HAS_PYGAME:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
    engine = _tts_engine
    if engine is not None:
        try:
            engine.stop()
        except Exception:
            pass


def _interrupted(generation):
    return generation != _generation


def is_speaking():
    """True while speech is queued, synthesised or playing (the mic must stay shut)."""
    return _speaking > 0


def _mark(delta):
    global _speaking
    with _speaking_lock:
        _speaking += delta


# ---- engines ---------------------------------------------------------------------------

EDGE_RETRY_SECONDS = 300           # after a failure, skip the online voice for this long
_edge_down_until = 0.0

# Piper (offline neural voice): settings "offline_voice", models in <data dir>/voices
PIPER_VOICE = "en_US-amy-medium"
_piper = {"voice": None, "name": None, "failed": None}
_piper_lock = threading.Lock()


def piper_model_path(name=None):
    from utils.paths import user_data_dir
    return os.path.join(user_data_dir(), "voices", (name or PIPER_VOICE) + ".onnx")


def piper_available(name=None):
    """piper-tts is installed and the voice model has been downloaded."""
    try:
        import importlib.util
        if importlib.util.find_spec("piper") is None:
            return False
    except (ImportError, ValueError):
        return False
    return os.path.isfile(piper_model_path(name))


def _piper_voice():
    """The loaded Piper voice (loaded once; about 2 s), or None."""
    name = PIPER_VOICE
    with _piper_lock:
        if _piper["voice"] is not None and _piper["name"] == name:
            return _piper["voice"]
        if _piper["failed"] == name or not piper_available(name):
            return None
        try:
            from piper import PiperVoice
            _piper.update(voice=PiperVoice.load(piper_model_path(name)), name=name, failed=None)
            logger.info("Offline voice %s loaded", name)
            return _piper["voice"]
        except Exception as exc:
            logger.warning("Couldn't load the offline voice %s: %s", name, exc)
            _piper.update(voice=None, name=None, failed=name)
            return None


def warm_up_offline_voice():
    """Load Piper in the background so the first offline sentence isn't slow."""
    if piper_available():
        threading.Thread(target=_piper_voice, name="hina-voice-warmup", daemon=True).start()


def _play(audio, hint, generation):
    """Play WAV/MP3 bytes; returns early if stop() is called."""
    if _interrupted(generation):
        return
    pygame.mixer.music.load(io.BytesIO(audio), hint)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if _interrupted(generation):
            pygame.mixer.music.stop()
            break
        time.sleep(0.05)
    pygame.mixer.music.unload()


def _edge_audio(text):
    """MP3 bytes of `text` from the online neural voice."""
    async def collect():
        out = bytearray()
        async for chunk in edge_tts.Communicate(text, voice_for(text)).stream():
            if chunk["type"] == "audio":
                out += chunk["data"]
        return bytes(out)
    audio = asyncio.run(collect())
    if not audio:
        raise RuntimeError("the neural voice returned no audio")
    return audio


def _piper_audio(text):
    """WAV bytes of `text` from the offline neural voice, or None if it isn't available."""
    voice = _piper_voice()
    if voice is None:
        return None
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        voice.synthesize_wav(text, wav)
    return buf.getvalue()


def _speak_sync(text):
    """Synchronous speech via pyttsx3 or fallback."""
    global _tts_engine
    clean = clean_text(text)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(clean)
        _tts_engine = engine
        try:
            engine.runAndWait()
        finally:
            _tts_engine = None
    except Exception:
        logger.warning("pyttsx3 fallback failed for: %s", clean)
        print(f"Hina (speak): {clean}")


def _speak_thread(text, generation=None):
    """Speak one utterance to completion (the caller has already _mark(1)'d)."""
    global _edge_down_until
    generation = _generation if generation is None else generation
    try:
        if _interrupted(generation):
            return  # stop() was called after this was queued
        clean = clean_text(text)
        if _HAS_EDGE_TTS and _HAS_PYGAME and time.time() >= _edge_down_until:
            try:
                _play(_edge_audio(clean), "mp3", generation)
                return
            except Exception as e:
                _edge_down_until = time.time() + EDGE_RETRY_SECONDS
                logger.warning("Neural voice failed (%s); using the offline voice for %d min",
                               e, EDGE_RETRY_SECONDS // 60)
        if _HAS_PYGAME:
            try:
                audio = _piper_audio(clean)
                if audio is not None:
                    _play(audio, "wav", generation)
                    return
            except Exception as e:
                logger.warning("Offline voice failed: %s", e)
        _speak_sync(clean)
    except Exception as e:
        logger.error("Speech synthesis failed: %s", e)
    finally:
        _mark(-1)


def _speaker_loop():
    while True:
        text, done, generation = _queue.get()
        try:
            _speak_thread(text, generation)
        finally:
            if done is not None:
                done.set()


def _ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_speaker_loop, name="hina-speaker", daemon=True)
            _worker.start()


def speak(text, blocking=False):
    """
    Queue text to be spoken, in order, by the single speaker thread.

    Args:
        text: The text to speak
        blocking: If True, wait until this utterance has been spoken (or stopped).
    """
    clean = clean_text(text)
    done = threading.Event() if blocking else None

    _mark(1)  # before queuing, so there is no gap the mic could slip into
    _ensure_worker()
    _queue.put((clean, done, _generation))

    if done is not None:
        done.wait()
