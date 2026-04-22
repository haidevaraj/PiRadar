import logging
import time
import threading
import re
from collections.abc import Callable
from datetime import datetime, time as clock_time
from pathlib import Path
from queue import Queue

import pygame
import requests

from airportdb_client import AirportDbClient
from formatter import build_alert_event, get_airline_name
from flight_database import FlightDatabase
from lcd_display import NullDisplay
import models
from models import FlightState
from opensky_client import OpenSkyClient
from text_to_speech import TextToSpeech


logger = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(
        self,
        assets_dir: Path,
        alert_volume: float,
        mixer_frequency: int,
        mixer_size: int,
        mixer_channels: int,
        mixer_buffer: int,
        silence_path: Path,
        status_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.assets_dir = assets_dir
        self.alert_volume = alert_volume
        self.mixer_frequency = mixer_frequency
        self.mixer_size = mixer_size
        self.mixer_channels = mixer_channels
        self.mixer_buffer = mixer_buffer
        self.silence_path = silence_path
        self.status_callback = status_callback
        self._enabled = False
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._initialize_mixer()

    def _initialize_mixer(self) -> None:
        try:
            pygame.mixer.init(
                frequency=self.mixer_frequency,
                size=self.mixer_size,
                channels=self.mixer_channels,
                buffer=self.mixer_buffer,
            )
        except pygame.error as exc:
            logger.warning("Could not initialize pygame audio: %s", exc)
            self._notify_status("Audio Error", "Init failed")
            return

        self._enabled = True
        self._start_background_silence()
        # Preload sound assets to avoid blocking on first play
        try:
            self._preload_sounds()
        except Exception:
            logger.exception("Preloading sounds failed")

    def _start_background_silence(self) -> None:
        if not self.silence_path.exists():
            logger.info(
                "No background silence track found at %s. Alert audio will still work.",
                self.silence_path,
            )
            return

        try:
            pygame.mixer.music.load(str(self.silence_path))
            pygame.mixer.music.set_volume(0.0)
            pygame.mixer.music.play(loops=-1)
        except pygame.error as exc:
            logger.warning("Could not start background silence track: %s", exc)
            self._notify_status("Audio Error", "Silence failed")

    def _preload_sounds(self) -> None:
        """Load all common audio files from assets_dir into memory to avoid latency on first play."""
        if not self.assets_dir or not Path(self.assets_dir).exists():
            return

        for path in Path(self.assets_dir).rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".wav", ".ogg", ".mp3"):
                continue
            sound_path = str(path)
            if sound_path in self._sounds:
                continue
            try:
                snd = pygame.mixer.Sound(sound_path)
                snd.set_volume(self.alert_volume)
                self._sounds[sound_path] = snd
            except Exception as exc:
                logger.debug("Failed to preload sound %s: %s", sound_path, exc)

    def play(self, sound_path: str) -> pygame.mixer.Channel | None:
        if not self._enabled:
            return None

        try:
            sound = self._sounds.get(sound_path)
            if sound is None:
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(self.alert_volume)
                self._sounds[sound_path] = sound
            channel = sound.play()
            return channel
        except pygame.error as exc:
            logger.warning("Could not play alert sound %s: %s", sound_path, exc)
            self._notify_status("Audio Error", "Play failed")
            return None

    def _notify_status(self, title: str, detail: str) -> None:
        if self.status_callback is not None:
            self.status_callback(title, detail)


class AlertCache:
    def __init__(self, cooldown_minutes: int) -> None:
        self.cooldown_seconds = cooldown_minutes * 60
        self.seen_flights: dict[str, float] = {}

    def should_alert(self, callsign: str) -> bool:
        now = time.time()
        previous_seen_at = self.seen_flights.get(callsign)
        if previous_seen_at is None or now - previous_seen_at >= self.cooldown_seconds:
            self.seen_flights[callsign] = now
            return True
        return False


class LocationService:
    def __init__(
        self,
        request_timeout_seconds: int = 5,
        user_agent: str = "FlightTracker/1.0",
        status_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.session = requests.Session()
        self.request_timeout_seconds = request_timeout_seconds
        self.user_agent = user_agent
        self.status_callback = status_callback

    def get_location_name(self, latitude: float, longitude: float) -> str:
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=json&lat={latitude}&lon={longitude}"
        )
        headers = {"User-Agent": self.user_agent}
        try:
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.request_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Could not resolve monitoring area name: %s", exc)
            self._notify_network_status(exc, "Location Err", "Lookup failed")
            return "Unknown"

        address = data.get("address", {})
        return (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("county")
            or address.get("state")
            or "Unknown"
        )

    def _notify_network_status(
        self,
        exc: requests.exceptions.RequestException,
        title: str,
        detail: str,
    ) -> None:
        if self.status_callback is None:
            return
        if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            self.status_callback("WiFi Error", "Network down")
            return
        self.status_callback(title, detail)


class FlightTracker:
    def __init__(
        self,
        client: OpenSkyClient,
        alert_cache: AlertCache,
        airline_map: dict[str, str],
        aircraft_type_map: dict[str, str],
        assets_dir: Path,
        latitude: float,
        longitude: float,
        radius_miles: int,
        poll_interval_seconds: int,
        snooze_start_time: clock_time,
        snooze_end_time: clock_time,
        location_service: LocationService | None = None,
        audio_player: AudioPlayer | None = None,
        flight_database: FlightDatabase | None = None,
        airportdb_client: AirportDbClient | None = None,
        display: NullDisplay | None = None,
        tts_player: TextToSpeech | None = None,
        enable_airline_announcement: bool = True,
        announcement_delay_seconds: float = 0.5,
        enable_airportdb_lookup: bool = True,
    ) -> None:
        self.client = client
        self.alert_cache = alert_cache
        self.airline_map = airline_map
        self.aircraft_type_map = aircraft_type_map
        self.assets_dir = assets_dir
        self.latitude = latitude
        self.longitude = longitude
        self.radius_miles = radius_miles
        self.poll_interval_seconds = poll_interval_seconds
        self.snooze_start_time = snooze_start_time
        self.snooze_end_time = snooze_end_time
        self._snooze_active = False
        self.location_service = location_service or LocationService()
        self.display = display or NullDisplay()
        self.location_service.status_callback = self._show_display_error
        self.audio_player = audio_player
        if self.audio_player is None:
            raise ValueError("FlightTracker requires an AudioPlayer instance.")
        self.airportdb_client = airportdb_client
        self.client.status_callback = self._show_display_error
        if self.airportdb_client is not None:
            self.airportdb_client.status_callback = self._show_display_error
        self.tts_player = tts_player or TextToSpeech(volume=100)
        self.enable_airline_announcement = enable_airline_announcement
        self.flight_database = flight_database or FlightDatabase(Path("data/flighttrackr.db"))
        
        # Remove FlightAware references
        self.flightaware_client = None
        
        # Lock to ensure only one alert (Sound + TTS) is processed at a time
        self._alert_lock = threading.Lock()
        
        # AirportDB configuration (free with internal caching)
        self.enable_airportdb_lookup = enable_airportdb_lookup

    def _play_announcement(
        self,
        airline: str,
        callsign: str,
        origin: str | None,
        destination: str | None,
        altitude: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        delay_minutes: int | None = None,
    ) -> None:
        """Play a single announcement to audio."""
        try:
            logger.info(
                "Playing announcement: %s %s %s -> %s (Alt: %s, Spd: %s, Hdg: %s, Delay: %s)",
                airline,
                callsign,
                origin,
                destination,
                altitude,
                speed,
                heading,
                delay_minutes,
            )
            self.tts_player.speak_flight_alert(
                airline_name=airline,
                callsign=callsign,
                origin=origin,
                destination=destination,
                altitude=altitude,
                speed=speed,
                heading=heading,
                delay_minutes=delay_minutes,
            )
            logger.info("Announcement completed")
        except Exception as exc:
            logger.error("Text-to-speech announcement failed: %s", exc)

    def _trim_airport_code(self, airport_label: str | None) -> str | None:
        """
        Trim airport ICAO code from formatted airport label.
        Example: "Birmingham-Shuttlesworth International Airport (KBHM)" -> "Birmingham-Shuttlesworth International Airport"
        """
        if not airport_label:
            return airport_label
        
        # Match and remove (XXXX) at the end where XXXX is the airport code
        trimmed = re.sub(r'\s*\([A-Z0-9]{4}\)\s*$', '', airport_label)
        return trimmed if trimmed else airport_label

    def _should_call_airportdb(self, flight_details: 'models.FlightDetails | None') -> bool:
        """
        Smart check to determine if an AirportDB resolution attempt is required.
        """
        if not self.enable_airportdb_lookup or self.airportdb_client is None:
            return False
        
        # If we have no details, we can't look up codes because OpenSky doesn't 
        # provide them. We only proceed if we have a record that needs name resolution.
        if not flight_details or (not flight_details.origin and not flight_details.destination):
            return False

        # 1. Check if the values actually look like 4-character ICAO codes that need enrichment.
        # This prevents redundant calls if the data is already a label or empty.
        def needs_lookup(code: str | None) -> bool:
            if not code:
                return False
            stripped = code.strip()
            return len(stripped) == 4 and stripped.isalnum()

        if not (needs_lookup(flight_details.origin) or needs_lookup(flight_details.destination)):
            return False

        return True

    def display_startup_banner(self) -> None:
        location = self.location_service.get_location_name(self.latitude, self.longitude)
        logger.info("Flight Tracker Started")
        logger.info("Monitoring area: %s (%s mile radius)", location, self.radius_miles)
        self.display.show_startup(self.radius_miles)

    def poll_once(self) -> None:
        flights = self.client.get_nearby_flights(
            latitude=self.latitude,
            longitude=self.longitude,
            radius_miles=self.radius_miles,
        )
        for flight in flights:
            if self.alert_cache.should_alert(flight.callsign):
                try:
                    self.emit_alert(flight)
                except Exception:
                    logger.exception(
                        "Unhandled error while emitting alert for callsign %s",
                        flight.callsign,
                    )
                    self._show_display_error("Alert Error", "Skipped flight")

    def emit_alert(self, flight: FlightState) -> None:
        # Use a lock to ensure that if multiple flights are detected, they alert one after another
        with self._alert_lock:
            flight_details = None
            airline = get_airline_name(flight.callsign, self.airline_map)
            
            # Query local flight database for cached enrichment data
            flight_details = self.flight_database.get_flight_details(flight.callsign)
            
            # If no cached data, optionally enrich from AirportDB (free)
            if self._should_call_airportdb(flight_details):
                enriched = self.airportdb_client.enrich_flight_details(flight_details or models.FlightDetails())
                if enriched:
                    flight_details = enriched
                    # Store the enriched data in local database for future use
                    if flight_details:
                        self.flight_database.store_flight_details(
                            callsign=flight.callsign,
                            origin=flight_details.origin,
                            destination=flight_details.destination,
                            aircraft_type=flight_details.aircraft_type,
                            delay_minutes=flight_details.delay_minutes
                        )
            
            if flight_details is not None:
                flight_details = models.FlightDetails(
                    origin=self._trim_airport_code(flight_details.origin),
                    destination=self._trim_airport_code(flight_details.destination),
                    aircraft_type=flight_details.aircraft_type,
                    delay_minutes=flight_details.delay_minutes,
                )

            alert = build_alert_event(
                flight, self.airline_map, self.aircraft_type_map, self.assets_dir, flight_details=flight_details
            )
            
            alert_channel = self.audio_player.play(alert.sound_path)
            self.display.show_alert(alert)
            
            # 1. Wait for chime to finish
            if alert_channel is not None:
                while alert_channel.get_busy():
                    time.sleep(0.01)
            
            # 2. Play announcement (now blocking)
            if self.enable_airline_announcement and airline and self.tts_player:
                origin = flight_details.origin if flight_details else None
                destination = flight_details.destination if flight_details else None
                self._play_announcement(
                    airline, 
                    flight.callsign, 
                    origin, 
                    destination,
                    altitude=flight.altitude_m,
                    speed=flight.velocity_ms,
                    heading=flight.heading_deg,
                    delay_minutes=flight_details.delay_minutes if flight_details else None
                )
            
            logger.info("\n----------------------------")
            logger.info("%s", alert.line_1)
            logger.info("%s", alert.line_2)

    def run_forever(self) -> None:
        self.display_startup_banner()
        while True:
            try:
                is_snoozed = self._is_snoozed_now()
                if is_snoozed and not self._snooze_active:
                    logger.info(
                        "Entering snooze window: skipping airplane checks between %s and %s.",
                        self.snooze_start_time.strftime("%I:%M %p"),
                        self.snooze_end_time.strftime("%I:%M %p"),
                    )
                elif not is_snoozed and self._snooze_active:
                    logger.info("Leaving snooze window: resuming airplane checks.")
                self.display.set_snooze_status(
                    active=is_snoozed,
                    until_text=self.snooze_end_time.strftime("%I:%M %p").lstrip("0"),
                )
                self._snooze_active = is_snoozed
                if is_snoozed:
                    pass
                else:
                    self.poll_once()
            except Exception:
                logger.exception("Unhandled error during poll cycle")
                self._show_display_error("Tracker Error", "Poll failed")
            self._wait_until_next_poll()

    def _is_snoozed_now(self) -> bool:
        current_time = datetime.now().time()
        if self.snooze_start_time == self.snooze_end_time:
            return False
        if self.snooze_start_time < self.snooze_end_time:
            return self.snooze_start_time <= current_time < self.snooze_end_time
        return current_time >= self.snooze_start_time or current_time < self.snooze_end_time

    def _show_display_error(self, title: str, detail: str) -> None:
        self.display.show_error(title, detail)

    def _wait_until_next_poll(self) -> None:
        deadline = time.monotonic() + self.poll_interval_seconds
        while True:
            try:
                self.display.idle_step()
            except Exception:
                logger.exception("Unhandled error during display idle update")
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.1, remaining))
