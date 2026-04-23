import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from airportdb_client import AirportDbClient
from settings_loader import (
    LoggingSettings,
    load_aircraft_type_map,
    load_airline_map,
    load_settings,
)
from flight_database import FlightDatabase
from lcd_display import build_display
from opensky_client import OpenSkyClient
from services import AlertCache, AudioPlayer, FlightTracker, LocationService
from route_updater import check_and_update_routes
from text_to_speech import TextToSpeech


def configure_logging(logging_settings: LoggingSettings, log_path: Path) -> None:
    formatter = logging.Formatter(logging_settings.format_string)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging_settings.level_name.upper())
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=logging_settings.max_bytes,
        backupCount=logging_settings.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def main() -> None:
    settings = load_settings()
    configure_logging(settings.logging, settings.paths.log_path)
    paths = settings.paths
    tracker_settings = settings.tracker
    opensky_settings = settings.opensky
    airportdb_settings = settings.airportdb
    location_settings = settings.location
    audio_settings = settings.audio
    display_settings = settings.display

    # Perform weekly route update check before initializing tracker
    check_and_update_routes(paths.airline_routes_path)

    tracker = FlightTracker(
        client=OpenSkyClient(
            client_id=opensky_settings.client_id,
            client_secret=opensky_settings.client_secret,
            min_request_interval_seconds=opensky_settings.min_request_interval_seconds,
            token_refresh_buffer_seconds=opensky_settings.token_refresh_buffer_seconds,
            auth_timeout_seconds=opensky_settings.auth_timeout_seconds,
            request_timeout_seconds=opensky_settings.request_timeout_seconds,
            rate_limit_backoff_seconds=opensky_settings.rate_limit_backoff_seconds,
            radius_degrees_per_mile=opensky_settings.radius_degrees_per_mile,
        ),
        alert_cache=AlertCache(tracker_settings.cooldown_minutes),
        airline_map=load_airline_map(paths.airline_map_path),
        aircraft_type_map=load_aircraft_type_map(paths.aircraft_type_map_path),
        airline_routes_path=paths.airline_routes_path,
        assets_dir=paths.assets_dir,
        latitude=tracker_settings.latitude,
        longitude=tracker_settings.longitude,
        radius_miles=tracker_settings.radius_miles,
        poll_interval_seconds=tracker_settings.poll_interval_seconds,
        snooze_start_time=tracker_settings.snooze_start_time,
        snooze_end_time=tracker_settings.snooze_end_time,
        location_service=LocationService(
            request_timeout_seconds=location_settings.request_timeout_seconds,
            user_agent=location_settings.user_agent,
        ),
        audio_player=AudioPlayer(
            assets_dir=paths.assets_dir,
            alert_volume=audio_settings.alert_volume,
            mixer_frequency=audio_settings.mixer_frequency,
            mixer_size=audio_settings.mixer_size,
            mixer_channels=audio_settings.mixer_channels,
            mixer_buffer=audio_settings.mixer_buffer,
            silence_path=paths.silent_audio_path,
        ),
        flight_database=FlightDatabase(paths.base_dir / "flighttrackr.db"),
        airportdb_client=AirportDbClient(
            api_token=airportdb_settings.api_token,
            master_db_path=paths.master_airport_db_path,
            cache_file=paths.airportdb_cache_file, 
            request_timeout_seconds=airportdb_settings.request_timeout_seconds,
        ),
        display=build_display(display_settings=display_settings, airplane_facts_path=paths.airplane_facts_path),
        tts_player=TextToSpeech(volume=100, language="en", tld="co.in"),
        enable_airline_announcement=True,
    )
    tracker.run_forever()


if __name__ == "__main__":
    main()
