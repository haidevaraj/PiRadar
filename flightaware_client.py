import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from models import FlightDetails


logger = logging.getLogger(__name__)


@dataclass
class FlightAwareUsage:
    month: str
    count: int


@dataclass
class FlightAwareCacheEntry:
    details: FlightDetails | None
    expires_at: datetime


class FlightAwareUsageTracker:
    def __init__(self, usage_file: Path, monthly_limit: int) -> None:
        self.usage_file = usage_file
        self.monthly_limit = max(0, monthly_limit)

    def try_consume(self, now: datetime | None = None) -> bool:
        usage = self._load(now=now)
        if usage.count >= self.monthly_limit:
            return False

        usage.count += 1
        self._save(usage)
        return True

    def remaining_calls(self, now: datetime | None = None) -> int:
        usage = self._load(now=now)
        return max(0, self.monthly_limit - usage.count)

    def _load(self, now: datetime | None = None) -> FlightAwareUsage:
        month = self._month_key(now=now)
        if not self.usage_file.exists():
            return FlightAwareUsage(month=month, count=0)

        try:
            with open(self.usage_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read FlightAware usage file: %s", exc)
            return FlightAwareUsage(month=month, count=0)

        saved_month = str(payload.get("month") or "")
        saved_count = int(payload.get("count") or 0)
        if saved_month != month:
            return FlightAwareUsage(month=month, count=0)
        return FlightAwareUsage(month=saved_month, count=max(0, saved_count))

    def _save(self, usage: FlightAwareUsage) -> None:
        payload = {"month": usage.month, "count": usage.count}
        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        except OSError as exc:
            logger.warning("Could not persist FlightAware usage file: %s", exc)

    def _month_key(self, now: datetime | None = None) -> str:
        timestamp = now or datetime.now(UTC)
        return timestamp.strftime("%Y-%m")


class FlightAwareClient:
    def __init__(
        self,
        api_key: str | None,
        usage_file: Path,
        cache_file: Path,
        monthly_limit: int,
        callsign_cache_ttl_minutes: int,
        request_timeout_seconds: int,
        lookup_window_days: int,
        max_pages: int,
        session: requests.Session | None = None,
        status_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.usage_tracker = FlightAwareUsageTracker(
            usage_file=usage_file,
            monthly_limit=monthly_limit,
        )
        self.cache_file = cache_file
        self.session = session or requests.Session()
        if self.api_key:
            self.session.headers.update({"x-apikey": self.api_key})
        self.callsign_cache_ttl = timedelta(minutes=max(0, callsign_cache_ttl_minutes))
        self.request_timeout_seconds = request_timeout_seconds
        self.lookup_window_days = lookup_window_days
        self.max_pages = max_pages
        self._cache: dict[str, FlightAwareCacheEntry] = self._load_cache()
        self._limit_reached_logged_month: str | None = None
        self.status_callback = status_callback

    def get_flight_details(self, callsign: str) -> FlightDetails | None:
        if not self.api_key:
            return None

        now = datetime.now(UTC)
        cached = self._cache.get(callsign)
        if cached is not None and now < cached.expires_at:
            logger.info(
                "FlightAware cache hit for %s. Using persistent data (expires %s).",
                callsign,
                cached.expires_at.strftime("%Y-%m-%d %H:%M")
            )
            return cached.details

        if not self.usage_tracker.try_consume(now=now):
            month = now.strftime("%Y-%m")
            if self._limit_reached_logged_month != month:
                logger.warning(
                    "FlightAware monthly lookup limit reached for %s. "
                    "Skipping further enrichments until next month.",
                    month,
                )
                self._notify_status("FltAware Cap", "1000/mo reached")
                self._limit_reached_logged_month = month
            return None

        self._limit_reached_logged_month = None
        details = self._fetch_flight_details(callsign=callsign, now=now)
        self._cache[callsign] = FlightAwareCacheEntry(
            details=details,
            expires_at=now + self.callsign_cache_ttl,
        )
        self._save_cache()
        return details

    def _load_cache(self) -> dict[str, FlightAwareCacheEntry]:
        if not self.cache_file.exists():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                cache = {}
                now = datetime.now(UTC)
                for k, v in data.items():
                    expires_at = datetime.fromisoformat(v["expires_at"])
                    if now < expires_at:
                        details = None
                        if v["details"]:
                            details = FlightDetails(**v["details"])
                        cache[k] = FlightAwareCacheEntry(details=details, expires_at=expires_at)
                return cache
        except Exception as exc:
            logger.warning("Could not load FlightAware cache: %s", exc)
            return {}

    def _save_cache(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            serializable = {}
            # Only save non-expired entries
            now = datetime.now(UTC)
            for k, v in self._cache.items():
                if now < v.expires_at:
                    details_dict = None
                    if v.details:
                        details_dict = {
                            "origin": v.details.origin,
                            "destination": v.details.destination,
                            "aircraft_type": v.details.aircraft_type
                        }
                    serializable[k] = {
                        "expires_at": v.expires_at.isoformat(),
                        "details": details_dict
                    }
            
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as exc:
            logger.warning("Could not save FlightAware cache: %s", exc)

    def _fetch_flight_details(self, callsign: str, now: datetime) -> FlightDetails | None:
        start = (now - timedelta(days=self.lookup_window_days)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=self.lookup_window_days)).strftime("%Y-%m-%d")
        url = (
            "https://aeroapi.flightaware.com/aeroapi/flights/"
            f"{quote(callsign)}?start={start}&end={end}&max_pages={self.max_pages}"
        )

        try:
            response = self.session.get(url, timeout=self.request_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("FlightAware lookup failed for %s: %s", callsign, exc)
            self._notify_request_status(exc, "FltAware Err", "Lookup failed")
            return None
        except ValueError as exc:
            logger.warning("FlightAware returned invalid JSON for %s: %s", callsign, exc)
            self._notify_status("FltAware Err", "Bad response")
            return None

        flights = payload.get("flights") or []
        if not flights:
            logger.info(
                "FlightAware returned no matching flight details for %s. "
                "%s lookups remain this month.",
                callsign,
                self.usage_tracker.remaining_calls(now=now),
            )
            return None

        best_match = self._select_best_match(flights, now=now)
        if len(flights) > 1:
            logger.info(
                "FlightAware selected %s leg %s -> %s from %s candidates (status=%s).",
                callsign,
                self._extract_airport_code(best_match.get("origin")) or "?",
                self._extract_airport_code(best_match.get("destination")) or "?",
                len(flights),
                best_match.get("status") or "unknown",
            )
        details = FlightDetails(
            origin=self._extract_airport_code(best_match.get("origin")),
            destination=self._extract_airport_code(best_match.get("destination")),
            aircraft_type=self._extract_aircraft_type(best_match),
        )
        logger.info(
            "FlightAware enriched %s (%s lookups left this month).",
            callsign,
            self.usage_tracker.remaining_calls(now=now),
        )
        if not any((details.origin, details.destination, details.aircraft_type)):
            return None
        return details

    def _select_best_match(self, flights: list[dict], now: datetime) -> dict:
        ranked_flights = sorted(
            flights,
            key=lambda flight: self._flight_match_score(flight, now=now),
            reverse=True,
        )
        for flight in ranked_flights:
            if flight.get("origin") or flight.get("destination") or flight.get("aircraft_type"):
                return flight
        return ranked_flights[0]

    def _flight_match_score(self, flight: dict, now: datetime) -> tuple[int, int, int, int]:
        is_active = self._is_active_flight(flight)
        has_route = int(bool(flight.get("origin") or flight.get("destination")))
        has_aircraft_type = int(bool(self._extract_aircraft_type(flight)))
        recency_score = -self._reference_time_distance_seconds(flight, now=now)
        return (int(is_active), has_route, has_aircraft_type, recency_score)

    def _is_active_flight(self, flight: dict) -> bool:
        status_text = str(flight.get("status") or "").strip().lower()
        if status_text:
            if any(word in status_text for word in ("cancel", "arriv", "complete", "land", "result")):
                return False
            if any(word in status_text for word in ("airborne", "en route", "depart", "taxi", "sched")):
                return True

        if self._coerce_bool(flight.get("cancelled")):
            return False

        actual_out = self._parse_timestamp(flight.get("actual_out"))
        actual_off = self._parse_timestamp(flight.get("actual_off"))
        actual_on = self._parse_timestamp(flight.get("actual_on"))
        actual_in = self._parse_timestamp(flight.get("actual_in"))

        if actual_on or actual_in:
            return False
        return bool(actual_out or actual_off)

    def _reference_time_distance_seconds(self, flight: dict, now: datetime) -> int:
        candidates = [
            self._parse_timestamp(flight.get(field))
            for field in (
                "actual_off",
                "estimated_off",
                "scheduled_off",
                "filed_departure_time",
                "actual_out",
                "estimated_out",
                "scheduled_out",
                "actual_on",
                "estimated_on",
                "scheduled_on",
                "actual_in",
                "estimated_in",
                "scheduled_in",
                "filed_arrival_time",
            )
        ]
        valid_candidates = [candidate for candidate in candidates if candidate is not None]
        if not valid_candidates:
            return 10**12
        return min(abs(int((candidate - now).total_seconds())) for candidate in valid_candidates)

    def _parse_timestamp(self, value: object) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

    def _coerce_bool(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False

    def _extract_airport_code(self, airport: object) -> str | None:
        if not isinstance(airport, dict):
            return None

        for field in ("code_icao", "code_iata", "code", "airport_code", "name"):
            value = airport.get(field)
            if value:
                return str(value).strip().upper()
        return None

    def _extract_aircraft_type(self, flight: dict) -> str | None:
        for field in ("aircraft_type", "type", "aircraft_type_iata"):
            value = flight.get(field)
            if value:
                return str(value).strip().upper()
        return None

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
