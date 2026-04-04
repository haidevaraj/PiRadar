import logging
import time
from collections.abc import Callable

import requests

from models import FlightState


logger = logging.getLogger(__name__)


class OpenSkyClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        min_request_interval_seconds: int,
        token_refresh_buffer_seconds: int = 300,
        auth_timeout_seconds: int = 10,
        request_timeout_seconds: int = 10,
        rate_limit_backoff_seconds: int = 60,
        radius_degrees_per_mile: float = 0.0145,
        status_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.min_request_interval_seconds = min_request_interval_seconds
        self.token_refresh_buffer_seconds = token_refresh_buffer_seconds
        self.auth_timeout_seconds = auth_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self.radius_degrees_per_mile = radius_degrees_per_mile
        self.access_token: str | None = None
        self.token_expires_at = 0.0
        self.last_request_time = 0.0
        self.session = requests.Session()
        self.status_callback = status_callback

    def get_access_token(self) -> str | None:
        if self.access_token and time.time() < (
            self.token_expires_at - self.token_refresh_buffer_seconds
        ):
            return self.access_token

        token_url = (
            "https://auth.opensky-network.org/auth/realms/opensky-network/"
            "protocol/openid-connect/token"
        )
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }

        try:
            response = self.session.post(token_url, data=data, timeout=self.auth_timeout_seconds)
            response.raise_for_status()
            token_data = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error("Error getting access token: %s", exc)
            self._notify_request_status(exc, "OpenSky Error", "Auth failed")
            return None

        self.access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = time.time() + expires_in
        return self.access_token

    def get_nearby_flights(
        self,
        latitude: float,
        longitude: float,
        radius_miles: int,
    ) -> list[FlightState]:
        token = self.get_access_token()
        if not token:
            logger.error("Failed to get access token, skipping request")
            self._notify_status("OpenSky Error", "No auth token")
            return []

        self._respect_rate_limit()

        radius_degrees = radius_miles * self.radius_degrees_per_mile
        url = (
            "https://opensky-network.org/api/states/all"
            f"?lamin={latitude - radius_degrees}"
            f"&lamax={latitude + radius_degrees}"
            f"&lomin={longitude - radius_degrees}"
            f"&lomax={longitude + radius_degrees}"
        )
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.session.get(url, headers=headers, timeout=self.request_timeout_seconds)
            self.last_request_time = time.time()

            if response.status_code == 429:
                logger.warning(
                    "Rate limited (429). Waiting %s seconds...",
                    self.rate_limit_backoff_seconds,
                )
                self._notify_status("OpenSky 429", f"Rate limit {self.rate_limit_backoff_seconds}s")
                time.sleep(self.rate_limit_backoff_seconds)
                return []

            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching data: %s", exc)
            self._notify_request_status(exc, "OpenSky Error", "Fetch failed")
            return []

        states = payload.get("states") or []
        flights: list[FlightState] = []
        for state in states:
            flight = FlightState.from_api_state(state)
            if flight:
                flights.append(flight)
        return flights

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval_seconds:
            time.sleep(self.min_request_interval_seconds - elapsed)

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
