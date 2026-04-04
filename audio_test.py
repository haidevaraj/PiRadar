import time

import pygame
from settings_loader import load_settings


settings = load_settings()
SILENT_FILE = str(settings.paths.silent_audio_path)
ALERT_FILE = str(settings.paths.alert_audio_path)

pygame.mixer.init(
    frequency=settings.audio.mixer_frequency,
    size=settings.audio.mixer_size,
    channels=settings.audio.mixer_channels,
    buffer=settings.audio.mixer_buffer,
)

# Keep the device open with a looping silent track
pygame.mixer.music.load(SILENT_FILE)
pygame.mixer.music.play(-1)

print("Silent loop running...")
time.sleep(2)

print("Playing alert...")
alert = pygame.mixer.Sound(ALERT_FILE)
alert.play()

time.sleep(5)
print("Done.")
