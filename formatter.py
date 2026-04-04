from datetime import datetime
from pathlib import Path

from models import AlertEvent, FlightDetails, FlightState


GENERIC_AIRCRAFT_TYPE_LABELS = {
    "GENERAL_AVIATION": "Type GA",
    "FIXED_WING_SINGLE_ENGINE": "Type Single",
    "FIXED_WING_MULTI_ENGINE": "Type Twin",
    "ROTORCRAFT": "Type Helo",
    "GLIDER": "Type Glider",
}
AIRCRAFT_MANUFACTURER_PREFIXES = (
    "AIRBUS ",
    "BOEING ",
    "BOMBARDIER ",
    "EMBRAER ",
    "CESSNA ",
    "BEECHCRAFT ",
    "DE HAVILLAND ",
    "MCDONNELL DOUGLAS ",
    "DOUGLAS ",
    "LOCKHEED ",
    "GULFSTREAM ",
    "DASSAULT ",
    "PIPER ",
)


def meters_to_feet(value: float) -> float:
    return value * 3.28084


def ms_to_mph(value: float) -> float:
    return value * 2.23694


def vertical_rate_to_fpm(value: float) -> float:
    return value * 196.850394


def format_optional_number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{round(value)}{suffix}"


def get_airline_name(callsign: str, airline_map: dict[str, str]) -> str | None:
    if not callsign or callsign == "N/A":
        return None
    return airline_map.get(callsign[:3].upper())


def format_primary_line(callsign: str, airline: str | None) -> str:
    return airline or callsign


def format_airline_display_line(callsign: str, airline: str | None) -> str:
    return airline or callsign


def format_vertical_rate(vertical_rate_ms: float | None) -> str:
    if vertical_rate_ms is None:
        return "VS N/A"

    vertical_rate_fpm = round(vertical_rate_to_fpm(vertical_rate_ms))
    return f"VS {vertical_rate_fpm:+}fpm"


def format_widget_value(labelled_value: str) -> str:
    _, _, value = labelled_value.partition(" ")
    return value or "N/A"


def format_secondary_line(current_time: str, callsign: str) -> str:
    return f"{current_time} {callsign}".strip()


def format_route(origin: str | None, destination: str | None) -> str | None:
    if origin and destination:
        return f"{origin} > {destination}"
    if origin:
        return f"{origin} > ?"
    if destination:
        return f"? > {destination}"
    return None


def normalize_aircraft_type(aircraft_type: str | None, aircraft_type_map: dict[str, str]) -> str | None:
    if not aircraft_type:
        return None
    normalized_type = aircraft_type.upper()
    mapped_type = aircraft_type_map.get(normalized_type, normalized_type)
    generic_label = GENERIC_AIRCRAFT_TYPE_LABELS.get(mapped_type.upper())
    if generic_label is not None:
        return generic_label

    cleaned_type = mapped_type.replace("_", " ")
    uppercase_cleaned_type = cleaned_type.upper()
    for prefix in AIRCRAFT_MANUFACTURER_PREFIXES:
        if uppercase_cleaned_type.startswith(prefix):
            return cleaned_type[len(prefix) :].strip()
    return cleaned_type


def format_detailed_secondary_line(
    current_time: str,
    callsign: str,
    flight_details: FlightDetails | None,
    altitude_ft: str,
    velocity_mph: str,
    heading_deg: str,
    vertical_rate_ms: float | None,
) -> str:
    route = format_route(
        flight_details.origin if flight_details else None,
        flight_details.destination if flight_details else None,
    )
    details = [
        current_time,
        callsign,
    ]
    if route:
        details.append(route)
    if flight_details and flight_details.aircraft_type:
        details.append(f"TYPE {flight_details.aircraft_type}")
    details.extend(
        [
            f"ALT {altitude_ft}",
            f"SPD {velocity_mph}",
            format_vertical_rate(vertical_rate_ms),
            f"HDG {heading_deg}",
        ]
    )
    return " | ".join(details)


def get_alert_sound(assets_dir: Path, squawk: str | None) -> Path:
    if squawk in {"7500", "7700"}:
        return assets_dir / "alert.mp3"
    return assets_dir / "chime.mp3"


def build_alert_event(
    flight: FlightState,
    airline_map: dict[str, str],
    aircraft_type_map: dict[str, str],
    assets_dir: Path,
    flight_details: FlightDetails | None = None,
    current_time: datetime | None = None,
) -> AlertEvent:
    airline = get_airline_name(flight.callsign, airline_map)
    altitude_ft = format_optional_number(
        meters_to_feet(flight.altitude_m) if flight.altitude_m is not None else None,
        "ft",
    )
    velocity_mph = format_optional_number(
        ms_to_mph(flight.velocity_ms) if flight.velocity_ms is not None else None,
        "mph",
    )
    heading_deg = format_optional_number(flight.heading_deg)
    timestamp = current_time or datetime.now()
    line_1 = format_primary_line(flight.callsign, airline)
    if flight_details and flight_details.aircraft_type:
        flight_details = FlightDetails(
            origin=flight_details.origin,
            destination=flight_details.destination,
            aircraft_type=normalize_aircraft_type(
                flight_details.aircraft_type,
                aircraft_type_map,
            ),
        )
    line_2 = format_detailed_secondary_line(
        timestamp.strftime("%I:%M %p"),
        flight.callsign,
        flight_details,
        altitude_ft,
        velocity_mph,
        heading_deg,
        flight.vertical_rate_ms,
    )

    return AlertEvent(
        callsign=flight.callsign,
        line_1=line_1,
        line_2=line_2,
        sound_path=str(get_alert_sound(assets_dir, flight.squawk)),
        title=flight.callsign,
        subtitle=format_airline_display_line(flight.callsign, airline),
        route=format_route(
            flight_details.origin if flight_details else None,
            flight_details.destination if flight_details else None,
        ),
        aircraft_type=flight_details.aircraft_type if flight_details else None,
        speed_text=format_widget_value(f"SPD {velocity_mph}"),
        heading_text=format_widget_value(f"HDG {heading_deg}"),
        altitude_text=format_widget_value(f"ALT {altitude_ft}"),
        vertical_rate_text=format_widget_value(format_vertical_rate(flight.vertical_rate_ms)),
    )
