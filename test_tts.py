#!/usr/bin/env python3
"""
Test script for TextToSpeech airline announcements.
Demonstrates how to use the TTS module to read airline names through the Sonos speaker.
"""

from text_to_speech import TextToSpeech

def test_airline_announcements():
    """Test various airline announcements."""
    
    tts = TextToSpeech(volume=100)
    
    # Example airlines
    test_cases = [
        ("Delta Airlines", "DAL123"),
        ("United Airlines", "UAL456"),
        ("American Airlines", "AAL789"),
        ("Southwest Airlines", "SWA234"),
        ("JetBlue Airways", "JBU567"),
    ]
    
    print("Testing airline announcements on Sonos speaker...")
    print("=" * 50)
    
    for airline_name, callsign in test_cases:
        print(f"\nAnnouncing: {airline_name} {callsign}")
        success = tts.speak_flight_alert(
            airline_name,
            callsign,
            origin="New Delhi Indira Gandhi Airport",
            destination="Mumbai Chhatrapati Shivaji Airport",
        )
        if success:
            print(f"✓ Successfully announced: {airline_name}")
        else:
            print(f"✗ Failed to announce: {airline_name}")
    
    print("\n" + "=" * 50)
    print("Test complete!")

if __name__ == "__main__":
    test_airline_announcements()
