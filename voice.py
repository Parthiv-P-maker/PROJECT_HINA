import asyncio
import os
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


async def _speak_async(text):
    filename = "hina_voice.mp3"

    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(filename)

    if _HAS_PYGAME:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        pygame.mixer.music.unload()

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
    """Run speech synthesis in a background thread."""
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


def speak(text, blocking=False):
    """
    Speak the given text.
    
    Args:
        text: The text to speak
        blocking: If True, block until speech completes. If False, run in background thread.
    """
    clean = clean_text(text)
    
    if not blocking:
        # Run in background thread to avoid blocking UI
        thread = threading.Thread(
            target=_speak_thread,
            args=(clean,),
            daemon=True
        )
        thread.start()
    else:
        # Blocking mode for testing or when needed
        if _HAS_EDGE_TTS and _HAS_PYGAME:
            try:
                asyncio.run(_speak_async(clean))
                return
            except Exception as e:
                logger.warning("edge_tts failed: %s", e)
        
        _speak_sync(clean)