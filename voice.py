import asyncio
import os

from utils.helpers import clean_text

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


def speak(text):
    clean = clean_text(text)
    if _HAS_EDGE_TTS and _HAS_PYGAME:
        try:
            asyncio.run(_speak_async(clean))
            return
        except Exception:
            pass

    # Fallbacks
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(clean)
        engine.runAndWait()
    except Exception:
        print(f"Hina (speak): {clean}")