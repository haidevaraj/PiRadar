#!/usr/bin/env python3
"""
Test script to simulate a complete flight alert with sound + TTS announcement.
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from services import AudioPlayer
from text_to_speech import TextToSpeech
from models import FlightState

def test_flight_alert_with_tts():
    """Test complete flight alert with notification sound + TTS announcement."""
    
    assets_dir = Path(__file__).parent / "assets"
    alert_sound = assets_dir / "alert.mp3"
    silent_sound = assets_dir / "silent.mp3"
    
    print("Testing Flight Alert with TTS Announcement")
    print("=" * 60)
    
    if not alert_sound.exists():
        print(f"⚠ Alert sound not found: {alert_sound}")
        return
    
    print(f"✓ Alert sound found: {alert_sound}")
    print(f"✓ Silent track: {silent_sound}")
    
    # Initialize audio player
    audio_player = AudioPlayer(
        assets_dir=assets_dir,
        alert_volume=1.0,
        mixer_frequency=22050,
        mixer_size=-16,
        mixer_channels=2,
        mixer_buffer=512,
        silence_path=silent_sound,
    )
    
    # Initialize TTS (use Indian English female voice via gTTS)
    tts = TextToSpeech(volume=100, language="en", tld="com")
    
    print("\n1. Playing alert sound...")
    audio_player.play(str(alert_sound))
    
    print("2. Waiting for alert sound to finish (2 seconds)...")
    time.sleep(2)
    
    print("3. Announcing airline via TTS...")
    success = tts.speak_flight_alert(
        airline_name="Southwest Airlines",
        callsign="SWA4389",
        origin="Hartsfield Jackson Atlanta International Airport",
        destination="San Antonio International Airport",
        altitude=10668, # Approx 35,000 feet
        speed=201.5,    # Approx 451 mph
        heading=180,    # South
        delay_minutes=15  # 15 minutes delayed
    )
    
    if success:
        print("✓ Flight alert complete!")
    else:
        print("✗ TTS announcement failed")
    
    print("\n" + "=" * 60)
    print("Test complete! You should have heard:")
    print("  1. Alert sound (beep)")
    print("  2. Female voice saying 'Southwest Airlines SWA4389 Hartsfield Jackson Atlanta International Airport -> San Antonio International Airport. Cruising at 35,000 feet, 451 miles per hour, heading south, 15 minutes delayed.'")

if __name__ == "__main__":
    test_flight_alert_with_tts()
