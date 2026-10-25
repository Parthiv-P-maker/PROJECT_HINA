import asyncio
import os
import queue
import tempfile
import threading

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


async def _speak_async(text, generation):
    # A unique file per utterance: nothing else can overwrite or delete it mid-play.
    handle, filename = tempfile.mkstemp(prefix="hina_voice_", suffix=".mp3")
    os.close(handle)
    try:
        communicate = edge_tts.Communicate(text, voice_for(text))
        await communicate.save(filename)

        if _HAS_PYGAME and not _interrupted(generation):
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                if _interrupted(generation):
                    pygame.mixer.music.stop()
                    break
                await asyncio.sleep(0.05)

            pygame.mixer.music.unload()
    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


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
    generation = _generation if generation is None else generation
    try:
        if _interrupted(generation):
            return  # stop() was called after this was queued
        clean = clean_text(text)
        if _HAS_EDGE_TTS and _HAS_PYGAME:
            try:
                asyncio.run(_speak_async(clean, generation))
                return
            except Exception as e:
                logger.warning("edge_tts failed: %s", e)

        # Fall back to pyttsx3
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
