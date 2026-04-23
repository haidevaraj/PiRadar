import json
import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for Python < 3.11
    import tomli as tomllib


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
CONFIG_PATH = BASE_DIR / "config.toml"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.toml"


@dataclass(frozen=True)
class PathSettings:
    base_dir: Path
    assets_dir: Path
    airline_map_path: Path
    airline_routes_path: Path
    aircraft_type_map_path: Path
    airplane_facts_path: Path
    log_path: Path
    flightaware_usage_file: Path
    flightaware_cache_file: Path
    master_airport_db_path: Path
    airportdb_cache_file: Path
    silent_audio_path: Path
    alert_audio_path: Path
    chime_audio_path: Path


@dataclass(frozen=True)
class LoggingSettings:
    level_name: str
    format_string: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class OpenSkySettings:
    client_id: str
    client_secret: str
    min_request_interval_seconds: int
    token_refresh_buffer_seconds: int
    auth_timeout_seconds: int
    request_timeout_seconds: int
    rate_limit_backoff_seconds: int
    radius_degrees_per_mile: float


@dataclass(frozen=True)
class FlightAwareSettings:
    api_key: str
    monthly_call_limit: int
    callsign_cache_ttl_minutes: int
    request_timeout_seconds: int
    lookup_window_days: int
    max_pages: int
    max_altitude_feet: int


@dataclass(frozen=True)
class AirportDbSettings:
    api_token: str
    request_timeout_seconds: int


@dataclass(frozen=True)
class LocationSettings:
    request_timeout_seconds: int
    user_agent: str


@dataclass(frozen=True)
class TrackerSettings:
    latitude: float
    longitude: float
    radius_miles: int
    cooldown_minutes: int
    poll_interval_seconds: int
    snooze_start_time: time
    snooze_end_time: time


@dataclass(frozen=True)
class AudioSettings:
    alert_volume: float
    mixer_frequency: int
    mixer_size: int
    mixer_channels: int
    mixer_buffer: int


@dataclass(frozen=True)
class DisplaySettings:
    enabled: bool
    i2c_bus: int
    i2c_address: int
    width: int
    height: int
    rotate: int
    backlight_timeout_seconds: int
    status_frame_seconds: float
    status_message_seconds: int
    alert_hold_seconds: int
    fact_rotate_seconds: int
    fact_wipe_frame_seconds: float
    recovery_retry_seconds: int
    snooze_message_frequency: int
    widget_labels: tuple[str, str, str, str]
    default_airplane_fact: str


@dataclass(frozen=True)
class Settings:
    paths: PathSettings
    logging: LoggingSettings
    opensky: OpenSkySettings
    flightaware: FlightAwareSettings
    airportdb: AirportDbSettings
    location: LocationSettings
    tracker: TrackerSettings
    audio: AudioSettings
    display: DisplaySettings


def _load_config_data() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Missing config file: {CONFIG_PATH}. Copy {CONFIG_EXAMPLE_PATH.name} to "
            f"{CONFIG_PATH.name} and fill in your own settings."
        )
    with open(CONFIG_PATH, "rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Config file must contain a TOML table: {CONFIG_PATH}")
    return payload


def _get_table(payload: dict, key: str) -> dict:
    table = payload.get(key, {})
    if not isinstance(table, dict):
        raise ValueError(f"Expected [{key}] to be a TOML table in {CONFIG_PATH}")
    return table


def _get_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_clock_time(value: str) -> time:
    hour_text, minute_text = value.strip().split(":", maxsplit=1)
    return time(hour=int(hour_text), minute=int(minute_text))


def _get_clock_time(name: str, default: time) -> time:
    value = os.getenv(name)
    if value is None:
        return default
    return _parse_clock_time(value)


def load_settings() -> Settings:
    payload = _load_config_data()
    api_keys_table = _get_table(payload, "api_keys")
    common_table = _get_table(payload, "common")
    paths_table = _get_table(payload, "paths")
    logging_table = _get_table(payload, "logging")
    opensky_advanced_table = _get_table(payload, "opensky_advanced")
    flightaware_advanced_table = _get_table(payload, "flightaware_advanced")
    airportdb_advanced_table = _get_table(payload, "airportdb_advanced")
    location_table = _get_table(payload, "location")
    audio_advanced_table = _get_table(payload, "audio_advanced")
    display_advanced_table = _get_table(payload, "display_advanced")

    paths = PathSettings(
        base_dir=BASE_DIR,
        assets_dir=ASSETS_DIR,
        airline_map_path=BASE_DIR / str(paths_table["airline_map_path"]),
        airline_routes_path=BASE_DIR / "assets/airline_routes.json",
        aircraft_type_map_path=BASE_DIR / str(paths_table["aircraft_type_map_path"]),
        airplane_facts_path=BASE_DIR / str(paths_table["airplane_facts_path"]),
        log_path=BASE_DIR / str(paths_table["log_path"]),
        flightaware_usage_file=BASE_DIR / str(paths_table["flightaware_usage_file"]),
        flightaware_cache_file=BASE_DIR / str(paths_table.get("flightaware_cache_file", "data/flightaware_cache.json")),
        master_airport_db_path=BASE_DIR / "assets/airports.json",
        airportdb_cache_file=BASE_DIR / str(paths_table["airportdb_cache_file"]),
        silent_audio_path=BASE_DIR / str(paths_table["silent_audio_path"]),
        alert_audio_path=BASE_DIR / str(paths_table["alert_audio_path"]),
        chime_audio_path=BASE_DIR / str(paths_table["chime_audio_path"]),
    )

    return Settings(
        paths=paths,
        logging=LoggingSettings(
            level_name=_get_str("FLIGHTTRACKR_LOG_LEVEL", str(logging_table["level_name"])),
            format_string=_get_str(
                "FLIGHTTRACKR_LOG_FORMAT",
                str(logging_table["format_string"]),
            ),
            max_bytes=_get_int("FLIGHTTRACKR_LOG_MAX_BYTES", int(logging_table["max_bytes"])),
            backup_count=_get_int("FLIGHTTRACKR_LOG_BACKUP_COUNT", int(logging_table["backup_count"])),
        ),
        opensky=OpenSkySettings(
            client_id=_get_str("OPENSKY_CLIENT_ID", str(api_keys_table["opensky_client_id"])),
            client_secret=_get_str(
                "OPENSKY_CLIENT_SECRET",
                str(api_keys_table["opensky_client_secret"]),
            ),
            min_request_interval_seconds=_get_int(
                "FLIGHTTRACKR_MIN_REQUEST_INTERVAL",
                int(opensky_advanced_table["min_request_interval_seconds"]),
            ),
            token_refresh_buffer_seconds=_get_int(
                "FLIGHTTRACKR_TOKEN_REFRESH_BUFFER_SECONDS",
                int(opensky_advanced_table["token_refresh_buffer_seconds"]),
            ),
            auth_timeout_seconds=_get_int(
                "FLIGHTTRACKR_OPENSKY_AUTH_TIMEOUT_SECONDS",
                int(opensky_advanced_table["auth_timeout_seconds"]),
            ),
            request_timeout_seconds=_get_int(
                "FLIGHTTRACKR_OPENSKY_REQUEST_TIMEOUT_SECONDS",
                int(opensky_advanced_table["request_timeout_seconds"]),
            ),
            rate_limit_backoff_seconds=_get_int(
                "FLIGHTTRACKR_OPENSKY_429_BACKOFF_SECONDS",
                int(opensky_advanced_table["rate_limit_backoff_seconds"]),
            ),
            radius_degrees_per_mile=_get_float(
                "FLIGHTTRACKR_RADIUS_DEGREES_PER_MILE",
                float(opensky_advanced_table["radius_degrees_per_mile"]),
            ),
        ),
        flightaware=FlightAwareSettings(
            api_key=_get_str(
                "FLIGHTAWARE_API_KEY",
                str(api_keys_table["flightaware_aeroapi_key"]),
            ),
            monthly_call_limit=_get_int(
                "FLIGHTAWARE_MONTHLY_CALL_LIMIT",
                int(common_table["monthly_call_limit"]),
            ),
            callsign_cache_ttl_minutes=_get_int(
                "FLIGHTAWARE_CACHE_TTL_MINUTES",
                int(flightaware_advanced_table["callsign_cache_ttl_minutes"]),
            ),
            request_timeout_seconds=_get_int(
                "FLIGHTAWARE_REQUEST_TIMEOUT_SECONDS",
                int(flightaware_advanced_table["request_timeout_seconds"]),
            ),
            lookup_window_days=_get_int(
                "FLIGHTAWARE_LOOKUP_WINDOW_DAYS",
                int(flightaware_advanced_table["lookup_window_days"]),
            ),
            max_pages=_get_int(
                "FLIGHTAWARE_MAX_PAGES",
                int(flightaware_advanced_table["max_pages"]),
            ),
            max_altitude_feet=_get_int(
                "FLIGHTAWARE_MAX_ALTITUDE_FEET",
                int(flightaware_advanced_table.get("max_altitude_feet", 0)),
            ),
        ),
        airportdb=AirportDbSettings(
            api_token=_get_str(
                "AIRPORTDB_API_TOKEN",
                str(api_keys_table["airportdb_api_token"]),
            ),
            request_timeout_seconds=_get_int(
                "AIRPORTDB_REQUEST_TIMEOUT_SECONDS",
                int(airportdb_advanced_table["request_timeout_seconds"]),
            ),
        ),
        location=LocationSettings(
            request_timeout_seconds=_get_int(
                "FLIGHTTRACKR_LOCATION_TIMEOUT_SECONDS",
                int(location_table["request_timeout_seconds"]),
            ),
            user_agent=_get_str(
                "FLIGHTTRACKR_LOCATION_USER_AGENT",
                str(location_table["user_agent"]),
            ),
        ),
        tracker=TrackerSettings(
            latitude=_get_float("FLIGHTTRACKR_LAT", float(common_table["latitude"])),
            longitude=_get_float("FLIGHTTRACKR_LON", float(common_table["longitude"])),
            radius_miles=_get_int("FLIGHTTRACKR_RADIUS", int(common_table["radius_miles"])),
            cooldown_minutes=_get_int(
                "FLIGHTTRACKR_COOLDOWN_MINUTES",
                int(common_table["cooldown_minutes"]),
            ),
            poll_interval_seconds=_get_int(
                "FLIGHTTRACKR_POLL_INTERVAL",
                int(common_table["poll_interval_seconds"]),
            ),
            snooze_start_time=_get_clock_time(
                "FLIGHTTRACKR_SNOOZE_START",
                _parse_clock_time(str(common_table["snooze_start_time"])),
            ),
            snooze_end_time=_get_clock_time(
                "FLIGHTTRACKR_SNOOZE_END",
                _parse_clock_time(str(common_table["snooze_end_time"])),
            ),
        ),
        audio=AudioSettings(
            alert_volume=_get_float("FLIGHTTRACKR_ALERT_VOLUME", float(common_table["alert_volume"])),
            mixer_frequency=_get_int(
                "FLIGHTTRACKR_AUDIO_FREQUENCY",
                int(audio_advanced_table["mixer_frequency"]),
            ),
            mixer_size=_get_int(
                "FLIGHTTRACKR_AUDIO_SAMPLE_SIZE",
                int(audio_advanced_table["mixer_size"]),
            ),
            mixer_channels=_get_int(
                "FLIGHTTRACKR_AUDIO_CHANNELS",
                int(audio_advanced_table["mixer_channels"]),
            ),
            mixer_buffer=_get_int(
                "FLIGHTTRACKR_AUDIO_BUFFER",
                int(audio_advanced_table["mixer_buffer"]),
            ),
        ),
        display=DisplaySettings(
            enabled=_get_bool("FLIGHTTRACKR_LCD_ENABLED", bool(common_table["display_enabled"])),
            i2c_bus=_get_int("FLIGHTTRACKR_LCD_I2C_BUS", int(display_advanced_table["i2c_bus"])),
            i2c_address=int(
                os.getenv("FLIGHTTRACKR_LCD_I2C_ADDRESS", str(display_advanced_table["i2c_address"])),
                0,
            ),
            rotate=_get_int("FLIGHTTRACKR_LCD_ROTATE", int(common_table["display_rotate"])),
            fact_rotate_seconds=_get_int(
                "FLIGHTTRACKR_LCD_FACT_ROTATE_SECONDS",
                int(common_table["display_fact_rotate_seconds"]),
            ),
            width=_get_int("FLIGHTTRACKR_LCD_WIDTH", int(display_advanced_table["width"])),
            height=_get_int("FLIGHTTRACKR_LCD_HEIGHT", int(display_advanced_table["height"])),
            backlight_timeout_seconds=_get_int(
                "FLIGHTTRACKR_LCD_BACKLIGHT_TIMEOUT",
                int(common_table["display_backlight_timeout_seconds"]),
            ),
            fact_wipe_frame_seconds=_get_float(
                "FLIGHTTRACKR_LCD_FACT_WIPE_FRAME_SECONDS",
                float(display_advanced_table["fact_wipe_frame_seconds"]),
            ),
            recovery_retry_seconds=_get_int(
                "FLIGHTTRACKR_LCD_RECOVERY_RETRY_SECONDS",
                int(display_advanced_table["recovery_retry_seconds"]),
            ),
            snooze_message_frequency=_get_int(
                "FLIGHTTRACKR_LCD_SNOOZE_MESSAGE_FREQUENCY",
                int(display_advanced_table["snooze_message_frequency"]),
            ),
            widget_labels=tuple(str(label) for label in display_advanced_table["widget_labels"]),
            default_airplane_fact=_get_str(
                "FLIGHTTRACKR_LCD_DEFAULT_FACT",
                str(display_advanced_table["default_airplane_fact"]),
            ),
            status_frame_seconds=_get_float(
                "FLIGHTTRACKR_LCD_STATUS_FRAME_SECONDS",
                float(display_advanced_table["status_frame_seconds"]),
            ),
            status_message_seconds=_get_int(
                "FLIGHTTRACKR_LCD_STATUS_MESSAGE_SECONDS",
                int(display_advanced_table["status_message_seconds"]),
            ),
            alert_hold_seconds=_get_int(
                "FLIGHTTRACKR_LCD_ALERT_HOLD_SECONDS",
                int(common_table["display_alert_hold_seconds"]),
            ),
        ),
    )


def load_airline_map(path: Path | None = None) -> dict[str, str]:
    file_path = path or (ASSETS_DIR / "icao_to_airline_names.json")
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_aircraft_type_map(path: Path | None = None) -> dict[str, str]:
    file_path = path or (ASSETS_DIR / "aircraft_types.json")
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
