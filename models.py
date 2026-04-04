from dataclasses import dataclass


@dataclass(frozen=True)
class FlightState:
    callsign: str
    altitude_m: float | None
    velocity_ms: float | None
    heading_deg: float | None
    vertical_rate_ms: float | None
    squawk: str | None

    @classmethod
    def from_api_state(cls, state: list) -> "FlightState | None":
        callsign = state[1].strip() if state[1] else None
        if not callsign:
            return None

        return cls(
            callsign=callsign,
            altitude_m=state[7],
            velocity_ms=state[9],
            heading_deg=state[10],
            vertical_rate_ms=state[11],
            squawk=state[14],
        )


@dataclass(frozen=True)
class FlightDetails:
    origin: str | None = None
    destination: str | None = None
    aircraft_type: str | None = None


@dataclass(frozen=True)
class AlertEvent:
    callsign: str
    line_1: str
    line_2: str
    sound_path: str
    title: str
    subtitle: str
    route: str | None
    aircraft_type: str | None
    speed_text: str
    heading_text: str
    altitude_text: str
    vertical_rate_text: str
