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

_speaking = 0
_speaking_lock = threading.Lock()

# One speaker thread drains this queue, so utterances never overlap or fight
# over the audio device. Items are (text, done_event_or_None).
_queue = queue.Queue()
_worker = None
_worker_lock = threading.Lock()


def is_speaking():
    """True while speech is queued, synthesised or playing (the mic must stay shut)."""
    return _speaking > 0


def _mark(delta):
    global _speaking
    with _speaking_lock:
        _speaking += delta


async def _speak_async(text):
    # A unique file per utterance: nothing else can overwrite or delete it mid-play.
    handle, filename = tempfile.mkstemp(prefix="hina_voice_", suffix=".mp3")
    os.close(handle)
    try:
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(filename)

        if _HAS_PYGAME:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)

            pygame.mixer.music.unload()
    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


def _speak_sync(text):
    """Synchronous speech via pyttsx3 or fallback."""
    clean = clean_text(text)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(clean)
        engine.runAndWait()
    except Exception:
        logger.warning("pyttsx3 fallback failed for: %s", clean)
        print(f"Hina (speak): {clean}")


def _speak_thread(text):
    """Speak one utterance to completion (the caller has already _mark(1)'d)."""
    try:
        clean = clean_text(text)
        if _HAS_EDGE_TTS and _HAS_PYGAME:
            try:
                asyncio.run(_speak_async(clean))
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
        text, done = _queue.get()
        try:
            _speak_thread(text)
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
        blocking: If True, wait until this utterance has been spoken.
    """
    clean = clean_text(text)
    done = threading.Event() if blocking else None

    _mark(1)  # before queuing, so there is no gap the mic could slip into
    _ensure_worker()
    _queue.put((clean, done))

    if done is not None:
        done.wait()
