import json
import logging
from collections.abc import Callable
from pathlib import Path

import requests

from models import FlightDetails


logger = logging.getLogger(__name__)


class AirportDbClient:
    def __init__(
        self,
        api_token: str | None,
        master_db_path: Path,
        cache_file: Path,
        request_timeout_seconds: int,
        session: requests.Session | None = None,
        status_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.api_token = (api_token or "").strip()
        self.master_db_path = master_db_path
        self.cache_file = cache_file
        self.request_timeout_seconds = request_timeout_seconds
        self.session = session or requests.Session()
        self.status_callback = status_callback
        self.airports_by_code = self._initialize_airport_data()

    def enrich_flight_details(self, flight_details: FlightDetails) -> FlightDetails:
        origin = self._resolve_airport_label(flight_details.origin)
        destination = self._resolve_airport_label(flight_details.destination)
        return FlightDetails(
            origin=origin,
            destination=destination,
            aircraft_type=flight_details.aircraft_type,
            delay_minutes=flight_details.delay_minutes,
        )

    def _resolve_airport_label(self, code: str | None) -> str | None:
        if not code:
            return None

        normalized_code = code.strip().upper()
        cached = self._get_cached_airport(normalized_code)
        if cached is not None:
            return self._build_label(cached, fallback=normalized_code)

        if not self.api_token or not self._looks_like_icao_code(normalized_code):
            return normalized_code

        airport = self._fetch_airport(normalized_code)
        if airport is None:
            return normalized_code
        return self._build_label(airport, fallback=normalized_code)

    def _initialize_airport_data(self) -> dict[str, dict[str, str]]:
        """Initialize airport data from master DB and then overlay user cache."""
        data = self._load_master_db()
        # Update with persistent user cache (which might have more detail or API overrides)
        cache_data = self._load_cache()
        data.update(cache_data)
        return data

    def _load_master_db(self) -> dict[str, dict[str, str]]:
        """Load static airport data from the local JSON file (mwgg/Airports format)."""
        if not self.master_db_path.exists():
            logger.info("Master airport database not found at %s. Skipping local DB load.", self.master_db_path)
            return {}

        try:
            with open(self.master_db_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
                
            # Map the mwgg/Airports format to our internal format
            airports = {}
            for code, details in payload.items():
                icao = str(details.get("icao") or code).upper()
                airports[icao] = {
                    "icao_code": icao,
                    "iata_code": str(details.get("iata") or "").upper(),
                    "name": str(details.get("name") or "").strip(),
                    "municipality": str(details.get("city") or "").strip(),
                    "iso_country": str(details.get("country") or "").strip().upper(),
                }
            logger.info("✓ Loaded %d airports from master database.", len(airports))
            return airports
        except Exception as exc:
            logger.warning("Could not read master airport database: %s", exc)
            return {}

    def _fetch_airport(self, code: str) -> dict[str, str] | None:
        url = f"https://airportdb.io/api/v1/airport/{code}?apiToken={self.api_token}"
        try:
            response = self.session.get(url, timeout=self.request_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("AirportDB lookup failed for %s: %s", code, exc)
            self._notify_request_status(exc, "AirportDB Err", "Lookup failed")
            return None
        except ValueError as exc:
            logger.warning("AirportDB returned invalid JSON for %s: %s", code, exc)
            self._notify_status("AirportDB Err", "Bad response")
            return None

        airport = {
            "icao_code": str(payload.get("icao_code") or payload.get("gps_code") or code).upper(),
            "iata_code": str(payload.get("iata_code") or "").upper(),
            "name": str(payload.get("name") or "").strip(),
            "municipality": str(payload.get("municipality") or "").strip(),
            "iso_country": str(payload.get("iso_country") or "").strip().upper(),
        }
        self._store_airport(airport)
        logger.info("AirportDB cached %s.", airport["icao_code"])
        return airport

    def _load_cache(self) -> dict[str, dict[str, str]]:
        if not self.cache_file.exists():
            return {}

        try:
            with open(self.cache_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read AirportDB cache file: %s", exc)
            return {}

        if not isinstance(payload, dict):
            return {}
        return {
            str(code).upper(): {
                "icao_code": str(details.get("icao_code") or code).upper(),
                "iata_code": str(details.get("iata_code") or "").upper(),
                "name": str(details.get("name") or "").strip(),
                "municipality": str(details.get("municipality") or "").strip(),
                "iso_country": str(details.get("iso_country") or "").strip().upper(),
            }
            for code, details in payload.items()
            if isinstance(details, dict)
        }

    def _store_airport(self, airport: dict[str, str]) -> None:
        icao_code = airport["icao_code"]
        self.airports_by_code[icao_code] = airport
        iata_code = airport.get("iata_code")
        if iata_code:
            self.airports_by_code[iata_code] = airport

        persisted = {
            code: details
            for code, details in sorted(self.airports_by_code.items())
            if self._looks_like_icao_code(code)
        }
        try:
            with open(self.cache_file, "w", encoding="utf-8") as handle:
                json.dump(persisted, handle, indent=2)
        except OSError as exc:
            logger.warning("Could not persist AirportDB cache file: %s", exc)

    def _get_cached_airport(self, code: str) -> dict[str, str] | None:
        return self.airports_by_code.get(code)

    def _build_label(self, airport: dict[str, str], fallback: str) -> str:
        name = airport.get("name") or ""
        icao_code = airport.get("icao_code") or fallback
        if name:
            return f"{name} ({icao_code})"
        return fallback

    def _looks_like_icao_code(self, code: str) -> bool:
        return len(code) == 4 and code.isalnum()

    def _notify_status(self, title: str, detail: str) -> None:
        if self.status_callback is not None:
            self.status_callback(title, detail)

    def _notify_request_status(
        self,
        exc: requests.exceptions.RequestException,
        title: str,
        detail: str,
    ) -> None:
        if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            self._notify_status("WiFi Error", "Network down")
            return
        self._notify_status(title, detail)
