import asyncio
import edge_tts
import pygame
import os
import re

pygame.mixer.init()

VOICE = "en-US-AriaNeural"


async def _speak_async(text):
    filename = "hina_voice.mp3"

    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(filename)

    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)

    pygame.mixer.music.unload()

    try:
        os.remove(filename)
    except:
        pass




def clean_text(text):
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    return text.strip()

def speak(text):
    clean = clean_text(text)
    asyncio.run(_speak_async(clean))