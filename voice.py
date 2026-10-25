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
        communicate = edge_tts.Communicate(text, VOICE)
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
