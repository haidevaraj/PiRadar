import json
import logging
import random
import time
from collections.abc import Callable
from pathlib import Path

from settings_loader import DisplaySettings
from models import AlertEvent


logger = logging.getLogger(__name__)


def _load_airplane_facts(path: Path, default_fact: str) -> tuple[str, ...]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load airplane facts from %s: %s", path, exc)
        return (default_fact,)

    if not isinstance(payload, list):
        logger.warning("Airplane facts file must contain a JSON array: %s", path)
        return (default_fact,)

    facts = tuple(
        str(item).strip()
        for item in payload
        if isinstance(item, str) and item.strip()
    )
    if not facts:
        logger.warning("Airplane facts file is empty: %s", path)
        return (default_fact,)
    return facts


class NullDisplay:
    def show_startup(self, radius_miles: int) -> None:
        return

    def show_alert(self, alert: AlertEvent) -> None:
        return

    def show_error(self, title: str, detail: str, duration_seconds: int = 10) -> None:
        return

    def set_snooze_status(self, active: bool, until_text: str) -> None:
        return

    def idle_step(self) -> None:
        return


class Ssd1309OledDisplay:
    def __init__(
        self,
        settings: DisplaySettings,
        airplane_facts_path: Path,
        bus_number: int = 1,
        address: int = 0x3C,
    ) -> None:
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1309
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            raise RuntimeError(
                "OLED dependencies are not installed. Run `pip install -r requirements.txt`."
            ) from exc

        self._image_module = Image
        self._draw_module = ImageDraw
        self._font_module = ImageFont
        self._settings = settings
        self._airplane_facts = _load_airplane_facts(
            airplane_facts_path,
            default_fact=settings.default_airplane_fact,
        )
        self._i2c_factory = i2c
        self._device_factory = ssd1309
        self._bus_number = bus_number
        self._rotate = settings.rotate
        self.width = settings.width
        self.height = settings.height
        self.address = address
        self._serial = None
        self._device = None
        self._measure_image = Image.new("1", (self.width, self.height))
        self._measure_draw = ImageDraw.Draw(self._measure_image)

        self._title_font = self._load_font(16)
        self._callsign_font = self._load_font(9)
        self._airline_font = self._load_font(10)
        self._subtitle_font = self._load_font(8)
        self._route_font = self._load_font(9)
        self._widget_label_font = self._load_font(8)
        self._widget_value_font = self._load_font(10)

        self._default_title = "FlightTrackr"
        self._default_status = "Scanning nearby traffic"
        self._mode = "idle"
        self._current_alert: AlertEvent | None = None
        self._current_alert_expires_at = 0.0
        self._temporary_message_expires_at = 0.0
        self._status_title = self._default_title
        self._status_detail = self._default_status
        self._status_frames: list[str] = []
        self._status_frame_index = 0
        self._fact_lines: list[str] = []
        self._showing_snooze_message = False
        self._snooze_active = False
        self._snooze_until_text = ""
        self._facts_since_snooze_message = 0
        self._random = random.Random()
        self._fact_cycle: list[int] = []
        self._next_fact_at = 0.0
        self._next_frame_at = 0.0
        self._display_available = True
        self._display_recovery_due_at = 0.0

        self._connect_device()
        self._render_status_screen(
            title=self._default_title,
            detail=self._default_status,
            footer="OLED ready",
        )

    def show_startup(self, radius_miles: int) -> None:
        self._mode = "startup"
        self._temporary_message_expires_at = (
            time.monotonic() + self._settings.status_message_seconds
        )
        self._set_status_message(
            title="FlightTrackr",
            detail=f"Radius {radius_miles} mi",
            footer="Waiting for traffic",
        )

    def show_alert(self, alert: AlertEvent) -> None:
        self._mode = "alert"
        self._temporary_message_expires_at = 0.0
        self._current_alert = alert
        self._current_alert_expires_at = time.monotonic() + self._settings.alert_hold_seconds
        self._prepare_status_frames(self._compose_alert_status(alert), width=122, continuous=True)
        self._render_alert_screen()

    def show_error(self, title: str, detail: str, duration_seconds: int = 10) -> None:
        self._mode = "error"
        self._temporary_message_expires_at = time.monotonic() + max(1, duration_seconds)
        self._set_status_message(title=title, detail=detail, footer="Will retry automatically")

    def set_snooze_status(self, active: bool, until_text: str) -> None:
        normalized_until_text = " ".join(until_text.split())
        if self._snooze_active == active and self._snooze_until_text == normalized_until_text:
            return

        self._snooze_active = active
        self._snooze_until_text = normalized_until_text
        self._facts_since_snooze_message = 0
        self._showing_snooze_message = False

    def idle_step(self) -> None:
        now = time.monotonic()

        if self._current_alert is not None and now >= self._current_alert_expires_at:
            self._clear_alert()
            self._show_idle_fact()
            return

        if self._temporary_message_expires_at and now >= self._temporary_message_expires_at:
            self._temporary_message_expires_at = 0.0
            if self._current_alert is not None:
                self._mode = "alert"
                self._render_alert_screen()
            else:
                self._show_idle_fact()
            return

        if now < self._next_frame_at:
            return

        if self._mode == "alert" and self._current_alert is not None and len(self._status_frames) > 1:
            self._status_frame_index = (self._status_frame_index + 1) % len(self._status_frames)
            self._render_alert_screen()
            self._next_frame_at = now + self._settings.status_frame_seconds
            return

        if self._mode == "idle" and now >= self._next_fact_at:
            self._show_idle_fact(next_fact=True)
            return

        if self._mode in {"startup", "error", "idle"} and len(self._status_frames) > 1:
            self._status_frame_index = (self._status_frame_index + 1) % len(self._status_frames)
            self._render_status_screen(
                title=self._status_title,
                detail=self._status_frames[self._status_frame_index],
                footer=self._status_detail,
            )
            self._next_frame_at = now + self._settings.status_frame_seconds

    def _set_status_message(self, title: str, detail: str, footer: str) -> None:
        self._status_title = title
        self._status_detail = footer
        self._prepare_status_frames(detail, width=118)
        self._render_status_screen(
            title=title,
            detail=self._status_frames[self._status_frame_index],
            footer=footer,
        )

    def _render_status_screen(self, title: str, detail: str, footer: str) -> None:
        image = self._image_module.new("1", (self.width, self.height), 0)
        draw = self._draw_module.Draw(image)

        draw.rounded_rectangle((0, 0, self.width - 1, self.height - 1), radius=6, outline=1, width=1)
        self._draw_centered_text(draw, 4, title, self._title_font)
        draw.line((4, 24, self.width - 5, 24), fill=1, width=1)
        self._draw_centered_text(draw, 30, detail, self._subtitle_font)
        draw.line((12, 46, self.width - 13, 46), fill=1, width=1)
        self._draw_centered_text(draw, 51, footer, self._widget_label_font)

        self._show_image(image)

    def _show_idle_fact(self, next_fact: bool = False) -> None:
        self._mode = "idle"
        if next_fact or not self._fact_lines:
            fact_text = self._next_idle_message()
        else:
            fact_text = " ".join(self._fact_lines)
        next_fact_lines = self._wrap_text_lines(
            fact_text,
            font=self._subtitle_font,
            width=112,
            max_lines=4,
        )
        if next_fact and self._fact_lines:
            self._animate_fact_wipe()
        self._fact_lines = next_fact_lines
        self._status_frames = []
        self._status_frame_index = 0
        self._render_idle_fact_screen()
        self._next_fact_at = time.monotonic() + self._settings.fact_rotate_seconds
        self._next_frame_at = self._next_fact_at

    def _clear_alert(self) -> None:
        self._current_alert = None
        self._current_alert_expires_at = 0.0

    def _next_airplane_fact(self) -> str:
        if not self._fact_cycle:
            self._fact_cycle = list(range(len(self._airplane_facts)))
            self._random.shuffle(self._fact_cycle)
        return self._airplane_facts[self._fact_cycle.pop()]

    def _next_idle_message(self) -> str:
        if self._snooze_active and self._facts_since_snooze_message >= self._settings.snooze_message_frequency:
            self._facts_since_snooze_message = 0
            self._showing_snooze_message = True
            return (
                "Snooze activated, tracking suspended until "
                f"{self._snooze_until_text}"
            )

        self._showing_snooze_message = False
        if self._snooze_active:
            self._facts_since_snooze_message += 1
        return self._next_airplane_fact()

    def _render_idle_fact_screen(self) -> None:
        image = self._build_idle_fact_image(self._fact_lines)
        self._show_image(image)

    def _build_idle_fact_image(self, fact_lines: list[str]):
        image = self._image_module.new("1", (self.width, self.height), 0)
        draw = self._draw_module.Draw(image)

        draw.rounded_rectangle((0, 0, self.width - 1, self.height - 1), radius=6, outline=1, width=1)
        line_height = 11
        block_height = len(fact_lines) * line_height
        start_y = max(8, (self.height - block_height) // 2)
        for index, line in enumerate(fact_lines):
            self._draw_centered_text(draw, start_y + (index * line_height), line, self._subtitle_font)
        return image

    def _animate_fact_wipe(self) -> None:
        base_image = self._build_idle_fact_image(self._fact_lines)
        plane_y = self.height // 2
        plane_length = 16
        for plane_x in range(-plane_length, self.width + plane_length + 1, 8):
            frame = base_image.copy()
            draw = self._draw_module.Draw(frame)
            wipe_right = min(self.width - 2, plane_x)
            if wipe_right > 1:
                draw.rectangle((1, 1, wipe_right, self.height - 2), fill=0)
            draw.rounded_rectangle((0, 0, self.width - 1, self.height - 1), radius=6, outline=1, width=1)
            self._draw_horizontal_plane(draw, plane_x, plane_y)
            self._show_image(frame)
            time.sleep(self._settings.fact_wipe_frame_seconds)

    def _draw_horizontal_plane(self, draw, nose_x: int, center_y: int) -> None:
        fuselage_left = nose_x - 16
        fuselage_right = nose_x
        top_y = center_y - 1
        bottom_y = center_y + 1

        # Fuselage and nose.
        draw.line((fuselage_left, top_y, fuselage_right - 2, top_y), fill=1, width=1)
        draw.line((fuselage_left, bottom_y, fuselage_right - 2, bottom_y), fill=1, width=1)
        draw.line((fuselage_left, top_y, fuselage_left, bottom_y), fill=1, width=1)
        draw.line((fuselage_right - 2, top_y, fuselage_right, center_y), fill=1, width=1)
        draw.line((fuselage_right - 2, bottom_y, fuselage_right, center_y), fill=1, width=1)

        # Main wing.
        wing_root_x = nose_x - 8
        draw.line((wing_root_x, center_y, wing_root_x - 6, center_y - 6), fill=1, width=1)
        draw.line((wing_root_x - 6, center_y - 6, wing_root_x - 11, center_y - 6), fill=1, width=1)
        draw.line((wing_root_x, center_y, wing_root_x - 6, center_y + 6), fill=1, width=1)
        draw.line((wing_root_x - 6, center_y + 6, wing_root_x - 11, center_y + 6), fill=1, width=1)

        # Tailplane and fin.
        tail_x = fuselage_left + 1
        draw.line((tail_x + 1, center_y, tail_x - 3, center_y - 3), fill=1, width=1)
        draw.line((tail_x + 1, center_y, tail_x - 3, center_y + 3), fill=1, width=1)
        draw.line((tail_x, center_y - 1, tail_x, center_y - 5), fill=1, width=1)

    def _render_alert_screen(self) -> None:
        if self._current_alert is None:
            return

        alert = self._current_alert
        image = self._image_module.new("1", (self.width, self.height), 0)
        draw = self._draw_module.Draw(image)

        callsign = self._fit_text(alert.title, self._callsign_font, 46)
        aircraft_type = self._fit_text(
            alert.aircraft_type or "",
            self._subtitle_font,
            70,
        )
        airline = self._fit_text(alert.subtitle, self._airline_font, 122)

        self._draw_left_text(draw, 2, 4, callsign, self._callsign_font)
        self._draw_right_text(draw, 1, self.width - 4, aircraft_type, self._subtitle_font)
        self._draw_centered_text(draw, 13, airline, self._airline_font)

        status_text = self._status_frames[self._status_frame_index] if self._status_frames else ""
        self._draw_centered_text(draw, 27, status_text, self._route_font)
        draw.line((0, 42, self.width - 1, 42), fill=1, width=1)

        values = (
            self._compact_speed(alert.speed_text),
            self._compact_heading(alert.heading_text),
            self._compact_altitude(alert.altitude_text),
            self._compact_vertical_rate(alert.vertical_rate_text),
        )
        self._draw_widgets(draw, values)
        self._show_image(image)

    def _show_image(self, image) -> None:
        if not self._ensure_device_ready():
            return
        try:
            self._device.display(image)
        except OSError as exc:
            self._mark_display_unavailable(exc)

    def _ensure_device_ready(self) -> bool:
        if self._display_available and self._device is not None:
            return True

        now = time.monotonic()
        if now < self._display_recovery_due_at:
            return False

        try:
            self._connect_device()
        except OSError as exc:
            self._mark_display_unavailable(exc, during_recovery=True)
            return False

        logger.info(
            "OLED display connection restored on I2C bus %s at address 0x%02X",
            self._bus_number,
            self.address,
        )
        return True

    def _connect_device(self) -> None:
        self._serial = self._i2c_factory(port=self._bus_number, address=self.address)
        self._device = self._device_factory(self._serial, width=self.width, height=self.height, rotate=self._rotate)
        self._display_available = True
        self._display_recovery_due_at = 0.0

    def _mark_display_unavailable(self, exc: OSError, during_recovery: bool = False) -> None:
        self._display_available = False
        self._device = None
        self._serial = None
        self._display_recovery_due_at = time.monotonic() + self._settings.recovery_retry_seconds
        if during_recovery:
            logger.warning(
                "OLED reconnect failed at address 0x%02X: %s. Retrying in %ss.",
                self.address,
                exc,
                self._settings.recovery_retry_seconds,
            )
            return
        logger.warning(
            "OLED I2C write failed at address 0x%02X: %s. Retrying in %ss.",
            self.address,
            exc,
            self._settings.recovery_retry_seconds,
        )

    def _draw_widgets(self, draw, values: tuple[str, str, str, str]) -> None:
        box_width = 30
        gap = 2
        top = 44
        bottom = self.height - 1

        for index, (label, value) in enumerate(zip(self._settings.widget_labels, values, strict=True)):
            left = index * (box_width + gap)
            right = left + box_width
            draw.line((left + 2, top, right - 2, top), fill=1, width=1)
            draw.line((left, top + 2, left, bottom - 2), fill=1, width=1)
            draw.line((right, top + 2, right, bottom - 2), fill=1, width=1)
            self._draw_centered_text(draw, top + 1, label, self._widget_label_font, left=left, right=right)
            self._draw_centered_text(draw, top + 9, value, self._widget_value_font, left=left, right=right)

    def _compose_alert_status(self, alert: AlertEvent) -> str:
        return alert.route or ""

    def _prepare_status_frames(self, text: str, width: int, continuous: bool = False) -> None:
        self._status_frames = self._build_scroll_frames(
            text=text,
            width=width,
            font=self._route_font,
            continuous=continuous,
        )
        self._status_frame_index = 0
        self._next_frame_at = time.monotonic() + self._settings.status_frame_seconds

    def _build_scroll_frames(self, text: str, width: int, font, continuous: bool = False) -> list[str]:
        normalized_text = " ".join(text.split()) or " "
        if self._text_width(normalized_text, font) <= width:
            return [normalized_text]

        average_char_width = max(1, self._text_width(normalized_text, font) // len(normalized_text))
        max_chars = max(8, width // average_char_width)
        gap = "   "
        scroll_text = f"{normalized_text}{gap}"
        if continuous:
            loop_text = scroll_text + normalized_text[:max_chars]
            return [loop_text[index : index + max_chars] for index in range(len(scroll_text))]
        frames = [
            scroll_text[index : index + max_chars]
            for index in range(len(scroll_text) - max_chars + 1)
        ]
        frames.append(normalized_text[:max_chars])
        return frames

    def _wrap_text_lines(self, text: str, font, width: int, max_lines: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        current_line = ""
        word_index = 0
        while word_index < len(words):
            word = words[word_index]
            candidate = word if not current_line else f"{current_line} {word}"
            if self._text_width(candidate, font) <= width:
                current_line = candidate
                word_index += 1
                continue
            if not current_line:
                current_line = self._fit_text(word, font, width)
                word_index += 1
            lines.append(current_line)
            current_line = ""
            if len(lines) == max_lines - 1:
                break

        if word_index < len(words):
            remaining_text = " ".join(words[word_index:])
            final_line = remaining_text if not current_line else f"{current_line} {remaining_text}"
        else:
            final_line = current_line

        if not final_line:
            return lines[:max_lines]

        if self._text_width(final_line, font) > width:
            final_line = self._fit_text(final_line, font, width)
        lines.append(final_line)
        return lines[:max_lines]

    def _draw_centered_text(
        self,
        draw,
        top: int,
        text: str,
        font,
        left: int = 0,
        right: int | None = None,
    ) -> None:
        right_edge = self.width - 1 if right is None else right
        available_width = right_edge - left + 1
        text_width = self._text_width(text, font)
        x = left + max(0, (available_width - text_width) // 2)
        draw.text((x, top), text, font=font, fill=1)

    def _draw_left_text(self, draw, top: int, left: int, text: str, font) -> None:
        draw.text((left, top), text, font=font, fill=1)

    def _draw_right_text(self, draw, top: int, right: int, text: str, font) -> None:
        text_width = self._text_width(text, font)
        x = max(0, right - text_width)
        draw.text((x, top), text, font=font, fill=1)

    def _fit_text(self, text: str, font, width: int) -> str:
        normalized_text = " ".join(text.split())
        if self._text_width(normalized_text, font) <= width:
            return normalized_text

        ellipsis = "..."
        while normalized_text and self._text_width(normalized_text + ellipsis, font) > width:
            normalized_text = normalized_text[:-1]
        return (normalized_text + ellipsis) if normalized_text else ellipsis

    def _text_width(self, text: str, font) -> int:
        left, _, right, _ = self._measure_draw.textbbox((0, 0), text, font=font)
        return right - left

    def _load_font(self, size: int):
        font_paths = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/Library/Fonts/Arial.ttf",
        )
        for font_path in font_paths:
            try:
                return self._font_module.truetype(font_path, size)
            except OSError:
                continue
        return self._font_module.load_default()

    def _compact_speed(self, text: str) -> str:
        return text.replace("mph", "")

    def _compact_heading(self, text: str) -> str:
        return text.replace("deg", "")

    def _compact_altitude(self, text: str) -> str:
        if text == "N/A":
            return text
        if not text.endswith("ft"):
            return text
        try:
            feet = int(text[:-2])
        except ValueError:
            return text
        if feet >= 10000:
            return f"{feet / 1000:.1f}k"
        return str(feet)

    def _compact_vertical_rate(self, text: str) -> str:
        if text == "N/A":
            return text
        if not text.endswith("fpm"):
            return text
        try:
            fpm = int(text[:-3])
        except ValueError:
            return text.replace("fpm", "")
        return f"{fpm / 1000:+.1f}k"


def build_display(
    display_settings: DisplaySettings,
    airplane_facts_path: Path,
    columns: int = 16,
    rows: int = 2,
    backlight_timeout_seconds: int = 30,
    status_callback: Callable[[str, str], None] | None = None,
) -> NullDisplay | Ssd1309OledDisplay:
    del columns, rows, backlight_timeout_seconds

    if not display_settings.enabled:
        return NullDisplay()

    try:
        display = Ssd1309OledDisplay(
            settings=display_settings,
            airplane_facts_path=airplane_facts_path,
            bus_number=display_settings.i2c_bus,
            address=display_settings.i2c_address,
        )
    except Exception as exc:
        logger.warning("Could not initialize SSD1309 OLED display: %s", exc)
        if status_callback is not None:
            status_callback("OLED Error", "Init failed")
        return NullDisplay()

    logger.info(
        "SSD1309 OLED display enabled on I2C bus %s at address 0x%02X",
        display_settings.i2c_bus,
        display_settings.i2c_address,
    )
    return display
