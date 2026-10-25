from typing import Any

import arrow

from config import DEFAULT_TERMINAL_WIDTH, TerminalStyle
from i18n import (
    DEFAULT_LANGUAGE,
    TRANSPORT_EMOJIS,
    WEATHER_EMOJIS,
    translate_international_message,
)
from models import DepartureData, StopPlaceState, WeatherData


def make_terminal_hyperlink(url: str, text: str) -> str:
    """Wraps text in OSC 8 ANSI escape sequence for clickable terminal hyperlinks."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


class DeparturePresenter:
    """Handles localization and terminal formatting for DepartureData."""

    def __init__(self, lang: str = DEFAULT_LANGUAGE, style: str = TerminalStyle.MODERN):
        self.lang = lang
        self.style = style

    def minutes_until_departure(self, expected_iso_str: str) -> str:
        """Calculates remaining minutes until departure based on expected time."""
        expected_time = arrow.get(expected_iso_str)
        now = arrow.now(expected_time.tzinfo)
        diff_seconds = (expected_time - now).total_seconds()
        minutes_left = int(diff_seconds // 60)

        if minutes_left <= 0:
            return translate_international_message("now", lang=self.lang)
        elif minutes_left == 1:
            return f"1 {translate_international_message('min', lang=self.lang)}"
        else:
            return f"{minutes_left} {translate_international_message('min', lang=self.lang)}"

    def format_transport_mode(self, transport_mode: str | None) -> str:
        """Formats transport mode with emoji and localized text."""
        mode_key = (transport_mode or "").lower()
        localized_name = translate_international_message(mode_key, lang=self.lang)
        if localized_name == mode_key:
            localized_name = mode_key.capitalize() or translate_international_message("unknown", lang=self.lang)

        match self.style:
            case TerminalStyle.MODERN:
                emoji = TRANSPORT_EMOJIS.get(mode_key, "🚏")
                return f"{emoji} {localized_name:<7}"
            case _:
                return f"{localized_name:<7}"

    def format_delay(self, aimed_raw: str, expected_raw: str) -> str:
        aimed = arrow.get(aimed_raw)
        expected = arrow.get(expected_raw)
        diff_seconds = (expected - aimed).total_seconds()
        delay_minutes = int(diff_seconds // 60)

        if self.style == TerminalStyle.MODERN:
            if delay_minutes > 0:
                return f"🔴 {delay_minutes} {translate_international_message('delayed', lang=self.lang)}"
            elif delay_minutes < 0:
                return f"💚 {abs(delay_minutes)} {translate_international_message('early', lang=self.lang)}"
            else:
                return f"💚 {translate_international_message('on_time', lang=self.lang)}"
        else:
            red = "\033[91m"
            green = "\033[92m"
            reset = "\033[0m"
            if delay_minutes > 0:
                return f"{red}[!] {delay_minutes} {translate_international_message('delayed', lang=self.lang)}{reset}"
            elif delay_minutes < 0:
                return f"{green}[+] {abs(delay_minutes)} {translate_international_message('early', lang=self.lang)}{reset}"
            else:
                return f"{green}[V] {translate_international_message('on_time', lang=self.lang)}{reset}"

    def format_departure_row(self, dep: DepartureData, has_fresh_data: bool) -> str:
        mode_str = self.format_transport_mode(dep.transport_mode)
        line_code = dep.line_code
        destination = dep.destination
        if destination == "unknown":
            destination = translate_international_message("unknown", lang=self.lang)

        aimed_clock = arrow.get(dep.aimed_iso).format("HH:mm")
        expected_clock = arrow.get(dep.expected_iso).format("HH:mm")

        if has_fresh_data:
            time_left = self.minutes_until_departure(dep.expected_iso)
            delay = self.format_delay(dep.aimed_iso, dep.expected_iso)

            if dep.is_realtime:
                return (
                    f"{mode_str} {line_code:<5} {destination:33}  "
                    f"{time_left:6}  {expected_clock} ({aimed_clock}) -- {delay:18}"
                )
            else:
                scheduled_time_left = self.minutes_until_departure(dep.aimed_iso)
                return (
                    f"{mode_str} {line_code:<5} {destination:33}  "
                    f"{scheduled_time_left:6}  {aimed_clock} -- {translate_international_message('no_realtime', lang=self.lang)}"
                )
        else:
            clock_lbl = translate_international_message("clock", lang=self.lang)
            sched_lbl = translate_international_message("scheduled", lang=self.lang)
            off_tag = translate_international_message("offline_tag", lang=self.lang)
            return (
                f"{mode_str} {line_code:<5} {destination:33}  "
                f"{clock_lbl}: {expected_clock} ({sched_lbl}: {aimed_clock}) [{off_tag}]"
            )


class WeatherPresenter:
    """Handles dynamic localization and formatting of WeatherData."""

    def __init__(self, lang: str = DEFAULT_LANGUAGE, style: str = TerminalStyle.MODERN):
        self.lang = lang
        self.style = style

    def degrees_to_wind_direction(self, degrees: float) -> tuple[str, str]:
        """Converts degrees to localized 16-point compass label and flow arrow."""
        compass_names = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        if self.lang in ("no", "sv"):
            compass_names = [
                "N", "NNØ", "NØ", "ØNØ", "Ø", "ØSØ", "SØ", "SSØ",
                "S", "SSV", "SV", "VSV", "V", "VNV", "NV", "NNV"
            ]
        elif self.lang == "fi":
            compass_names = [
                "P", "PPO", "PO", "I-PO", "I", "I-KA", "KA", "E-KA",
                "E", "E-LO", "LO", "L-LO", "L", "L-LU", "LU", "P-LU"
            ]

        arrows = [
            "↓", "↙", "↙", "↙", "←", "↖", "↖", "↖",
            "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘"
        ]

        index = int((degrees + 11.25) % 360 // 22.5)
        return compass_names[index], arrows[index]

    def format_header(self, weather: WeatherData | None) -> str:
        """Formats localized weather summary for stop place header."""
        if not weather:
            return ""

        base_code = weather.symbol_code.split("_")[0]
        emoji = WEATHER_EMOJIS.get(base_code, "🌡️")
        desc = translate_international_message(base_code, lang=self.lang)
        if desc == base_code:
            desc = weather.symbol_code.capitalize()

        wind_text, wind_arrow = self.degrees_to_wind_direction(weather.wind_direction_degrees)

        if weather.wind_gust_ms and weather.wind_gust_ms > weather.wind_ms:
            wind_str = f"{weather.wind_ms:.1f} ({weather.wind_gust_ms:.1f}) m/s"
        else:
            wind_str = f"{weather.wind_ms:.1f} m/s"

        degrees_int = int(round(weather.wind_direction_degrees))

        if self.style == TerminalStyle.MODERN:
            return (
                f" ({emoji} {weather.temperature_c:.0f}°C, {desc}, "
                f"💨 {wind_str} {wind_arrow} {wind_text} {degrees_int}°)"
            )
        else:
            return (
                f" ({weather.temperature_c:.0f}C, {desc}, "
                f"{wind_str} {wind_text} {degrees_int}deg)"
            )


class StopPlacePresenter:
    """Coordinates rendering of header, errors, and departures for a stop place."""

    def __init__(
        self,
        lang: str = DEFAULT_LANGUAGE,
        style: str = TerminalStyle.MODERN,
        terminal_width: int = DEFAULT_TERMINAL_WIDTH,
    ):
        self.lang = lang
        self.style = style
        self.terminal_width = terminal_width
        self.dep_presenter = DeparturePresenter(lang=lang, style=style)
        self.weather_presenter = WeatherPresenter(lang=lang, style=style)

    def render(self, state: StopPlaceState) -> None:
        has_fresh_data = state.error_message is None and state.normalized_data is not None
        norm = state.normalized_data

        display_name = norm.name if norm and norm.name else state.name
        weather_text = self.weather_presenter.format_header(state.weather)

        yr_url: str | None = None
        if norm and norm.latitude is not None and norm.longitude is not None:
            yr_url = f"https://www.yr.no/nb/værvarsel/daglig-tabell/{norm.latitude:.4f},{norm.longitude:.4f}"

        if yr_url and self.style == TerminalStyle.MODERN:
            linked_name = make_terminal_hyperlink(yr_url, display_name)
            linked_pin = make_terminal_hyperlink(yr_url, "📍")
            visible_length = len(f" {display_name}{weather_text} ")
            side_dashes = max(1, (self.terminal_width - visible_length) // 2)
            left = "-" * side_dashes
            right = "-" * (self.terminal_width - visible_length - side_dashes)
            print(f"{left} {linked_name}{weather_text} {right}{linked_pin}")
        else:
            header_text = f" {display_name}{weather_text} "
            print(f"{header_text:-^{self.terminal_width}}📍")

        if state.error_message:
            yellow = "\033[93m" if self.style != TerminalStyle.CLASSIC else ""
            reset = "\033[0m" if self.style != TerminalStyle.CLASSIC else ""

            if state.error_message.startswith("NOT_FOUND:"):
                icon = "❓" if self.style != TerminalStyle.CLASSIC else "[?]"
                err_msg = translate_international_message(
                    "stop_not_found", lang=self.lang, id=state.clean_id, provider=state.provider
                )
                print(f" {yellow}{icon} {err_msg}{reset}")
                return
            elif state.error_message.startswith("API_ERROR:"):
                icon = "⚠️" if self.style != TerminalStyle.CLASSIC else "[!]"
                detalj = state.error_message.split(":", 1)[1]
                print(f" {yellow}{icon} API feil ({state.provider}): {detalj[:80]}{reset}")
                return
            elif state.normalized_data and state.last_updated_iso:
                last_time = arrow.get(state.last_updated_iso).format("HH:mm:ss")
                icon = "📡" if self.style != TerminalStyle.CLASSIC else "[!]"
                warn_msg = translate_international_message("offline_warn", lang=self.lang, time=last_time)
                print(f" {yellow}{icon} {warn_msg}{reset}")
            else:
                icon = "📡" if self.style != TerminalStyle.CLASSIC else "[X]"
                err_msg = translate_international_message("offline_err", lang=self.lang, name=display_name)
                print(f" {icon} {err_msg}")
                return

        if not norm:
            print(f"  {translate_international_message('no_data', lang=self.lang)}")
            return

        departures = norm.departures
        if not departures:
            print(f"  {translate_international_message('no_departures', lang=self.lang)}")
            return

        for dep in departures:
            row = self.dep_presenter.format_departure_row(dep, has_fresh_data=has_fresh_data)
            print(row)
