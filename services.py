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
from flightaware_client import FlightAwareClient
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

    def play(self, sound_path: str) -> None:
        if not self._enabled:
            return

        try:
            sound = self._sounds.get(sound_path)
            if sound is None:
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(self.alert_volume)
                self._sounds[sound_path] = sound
            sound.play()
        except pygame.error as exc:
            logger.warning("Could not play alert sound %s: %s", sound_path, exc)
            self._notify_status("Audio Error", "Play failed")

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
        flightaware_client: FlightAwareClient | None = None,
        airportdb_client: AirportDbClient | None = None,
        display: NullDisplay | None = None,
        tts_player: TextToSpeech | None = None,
        enable_airline_announcement: bool = True,
        announcement_delay_seconds: float = 0.5,
        enable_airportdb_lookup: bool = True,
        airportdb_throttle_minutes: int = 1,
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
        self.flightaware_client = flightaware_client
        self.airportdb_client = airportdb_client
        self.client.status_callback = self._show_display_error
        if self.flightaware_client is not None:
            self.flightaware_client.status_callback = self._show_display_error
        if self.airportdb_client is not None:
            self.airportdb_client.status_callback = self._show_display_error
        self.tts_player = tts_player or TextToSpeech(volume=100)
        self.enable_airline_announcement = enable_airline_announcement
        
        # Sequential announcement processing
        self._announcement_queue: Queue = Queue()
        self._announcement_lock = threading.Lock()
        self._announcement_thread_active = False
        self._start_announcement_processor()
        
        # AirportDB throttling configuration
        self.enable_airportdb_lookup = enable_airportdb_lookup
        self.airportdb_throttle_seconds = airportdb_throttle_minutes * 60
        self.last_airportdb_call_time = 0.0
        self.announcement_delay_seconds = announcement_delay_seconds

    def _start_announcement_processor(self) -> None:
        """Start the background thread that processes announcements sequentially."""
        if self._announcement_thread_active:
            return
        self._announcement_thread_active = True
        processor_thread = threading.Thread(
            target=self._announcement_processor_loop,
            daemon=True,
        )
        processor_thread.start()

    def _announcement_processor_loop(self) -> None:
        """Process announcements one at a time from the queue."""
        while self._announcement_thread_active:
            try:
                # Get next announcement (blocks until available)
                announcement = self._announcement_queue.get(timeout=0.5)
                if announcement is None:
                    # Sentinel value to stop
                    break
                airline, callsign, origin, destination = announcement
                self._play_announcement(airline, callsign, origin, destination)
            except Exception:
                # Queue timeout, continue looping
                pass

    def _play_announcement(
        self,
        airline: str,
        callsign: str,
        origin: str | None,
        destination: str | None,
    ) -> None:
        """Play a single announcement to audio."""
        try:
            # Wait for alert sound to finish (typical alert sound is ~0.3 seconds)
            time.sleep(0.3)
            logger.info(
                "Playing announcement: %s %s %s -> %s",
                airline,
                callsign,
                origin,
                destination,
            )
            self.tts_player.speak_flight_alert(airline, callsign, origin, destination)
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
        Smart check to determine if AirportDB lookup is necessary.
        Avoid unnecessary API calls.
        """
        if not self.enable_airportdb_lookup or self.airportdb_client is None:
            return False
        
        if flight_details is None:
            return False
        
        # Check throttling
        now = time.time()
        if now - self.last_airportdb_call_time < self.airportdb_throttle_seconds:
            logger.debug("AirportDB call throttled (%.0f seconds remaining)", 
                        self.airportdb_throttle_seconds - (now - self.last_airportdb_call_time))
            return False
        
        # Only call if we have airport codes to look up
        has_airport_data = flight_details.origin or flight_details.destination
        return bool(has_airport_data)

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
        flight_details = None
        airline = get_airline_name(flight.callsign, self.airline_map)
        if airline and self.flightaware_client is not None:
            flight_details = self.flightaware_client.get_flight_details(flight.callsign)
        
        # Only call AirportDB if smart checks allow it (throttled + necessary)
        if self._should_call_airportdb(flight_details):
            self.last_airportdb_call_time = time.time()
            flight_details = self.airportdb_client.enrich_flight_details(flight_details)
        
        # Trim airport codes from labels for display
        if flight_details is not None:
            flight_details = models.FlightDetails(
                origin=self._trim_airport_code(flight_details.origin),
                destination=self._trim_airport_code(flight_details.destination),
                aircraft_type=flight_details.aircraft_type,
            )

        alert = build_alert_event(
            flight,
            self.airline_map,
            self.aircraft_type_map,
            self.assets_dir,
            flight_details=flight_details,
        )
        self.audio_player.play(alert.sound_path)
        
        # Queue announcement for sequential processing (no delay, queue manages it)
        if self.enable_airline_announcement and airline and self.tts_player:
            origin = flight_details.origin if flight_details is not None else None
            destination = flight_details.destination if flight_details is not None else None
            self._announcement_queue.put((airline, flight.callsign, origin, destination))
        
        self.display.show_alert(alert)
        logger.info("\n----------------------------")
        logger.info("%s", alert.line_1)
        logger.info("%s", alert.line_2)

    def _announce_airline_in_background(
        self,
        airline: str,
        callsign: str,
        origin: str | None,
        destination: str | None,
    ) -> None:
        """Announce airline name after alert sound plays (in background thread)."""
        try:
            # Wait 1 second for alert sound to finish playing
            time.sleep(1.5)
            logger.info(
                "Starting airline announcement: %s %s %s -> %s",
                airline,
                callsign,
                origin,
                destination,
            )
            self.tts_player.speak_flight_alert(airline, callsign, origin, destination)
            logger.info("Airline announcement completed")
        except Exception as exc:
            logger.error("Text-to-speech announcement failed: %s", exc)

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
