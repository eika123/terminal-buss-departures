import arrow

from config import (
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TRANSIT_NAMING_STYLE,
    DEFAULT_TRANSPORT_MODE_MAX_WIDTH,
    DEFAULT_USE_NORMALIZED_STOP_NAMES,
    DESTINATION_MAX_WIDTH,
    TerminalStyle,
)
from i18n import (
    DEFAULT_LANGUAGE,
    TRANSPORT_EMOJIS,
    WEATHER_EMOJIS,
    translate_international_message,
)
from models import DepartureData, NormalizedStopData, StopPlaceState, WeatherData
from transit_identities import detect_transit_system, resolve_transit_term


def make_terminal_hyperlink(url: str, text: str) -> str:
    """Wraps text in OSC 8 ANSI escape sequence for clickable terminal hyperlinks."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


class DeparturePresenter:
    """Handles localization and terminal formatting for DepartureData."""

    def __init__(
        self,
        lang: str = DEFAULT_LANGUAGE,
        style: str = TerminalStyle.MODERN,
        mode_max_width: int = DEFAULT_TRANSPORT_MODE_MAX_WIDTH,
        naming_style: str = DEFAULT_TRANSIT_NAMING_STYLE,
        mode_overrides: dict[str, str] | None = None,
        system_overrides: dict[str, str] | None = None,
    ):
        self.lang = lang
        self.style = style
        self.mode_max_width = mode_max_width
        self.naming_style = naming_style
        self.mode_overrides = mode_overrides or {}
        self.system_overrides = system_overrides or {}

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

    def format_transport_mode(
        self, transport_mode: str | None, system_id: str | None = None
    ) -> str:
        """Formats transport mode with emoji and localized text, truncating if exceeding mode_max_width."""
        mode_key = (transport_mode or "").lower()
        localized_name = resolve_transit_term(
            mode=mode_key,
            system_id=system_id,
            user_lang=self.lang,
            naming_style=self.naming_style,
            mode_overrides=self.mode_overrides,
            system_overrides=self.system_overrides,
        )

        if len(localized_name) > self.mode_max_width:
            match localized_name:
                case "Spårvagn" if self.mode_max_width >= 6:
                    display_name = "Spårv."
                case "Tunnelbana" if self.mode_max_width >= 5:
                    display_name = "Tunn."
                case _:
                    display_name = (
                        f"{localized_name[: max(1, self.mode_max_width - 1)]}."
                    )
        else:
            display_name = localized_name

        match self.style:
            case TerminalStyle.MODERN:
                emoji = TRANSPORT_EMOJIS.get(mode_key, "🚏")
                return f"{emoji} {display_name:<{self.mode_max_width}}"
            case _:
                return f"{display_name:<{self.mode_max_width}}"

    def format_delay(self, aimed_raw: str, expected_raw: str) -> str:
        aimed = arrow.get(aimed_raw)
        expected = arrow.get(expected_raw)
        diff_seconds = (expected - aimed).total_seconds()
        delay_minutes = int(diff_seconds // 60)

        if delay_minutes > 0:
            msg = f"{delay_minutes} {translate_international_message('delayed', lang=self.lang)}"
            return (
                f"🔴 {msg}"
                if self.style == TerminalStyle.MODERN
                else f"\033[91m[!] {msg}\033[0m"
            )
        if delay_minutes < 0:
            msg = f"{abs(delay_minutes)} {translate_international_message('early', lang=self.lang)}"
            return (
                f"💚 {msg}"
                if self.style == TerminalStyle.MODERN
                else f"\033[92m[+] {msg}\033[0m"
            )

        msg = translate_international_message("on_time", lang=self.lang)
        return (
            f"💚 {msg}"
            if self.style == TerminalStyle.MODERN
            else f"\033[92m[V] {msg}\033[0m"
        )

    def format_departure_row(
        self, dep: DepartureData, has_fresh_data: bool, system_id: str | None = None
    ) -> str:
        mode_str = self.format_transport_mode(dep.transport_mode, system_id=system_id)
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
                exp_str = f"{expected_clock:<5}"
                aim_str = f"({aimed_clock})"
                status_str = f"   {delay}"
            else:
                exp_str = " " * 5
                aim_str = f"({aimed_clock})"
                status_str = f"   {translate_international_message('no_realtime', lang=self.lang)}"
                time_left = self.minutes_until_departure(dep.aimed_iso)

            dest_display = destination[: (DESTINATION_MAX_WIDTH - 1)]
            return (
                f"{mode_str} {line_code:>5}  {dest_display:<{DESTINATION_MAX_WIDTH}}  "
                f"{time_left:>7}  {exp_str} {aim_str} {status_str}"
            )
        else:
            clock_lbl = translate_international_message("clock", lang=self.lang)
            sched_lbl = translate_international_message("scheduled", lang=self.lang)
            off_tag = translate_international_message("offline_tag", lang=self.lang)
            return (
                f"{mode_str} {line_code:>5}  {destination:{DESTINATION_MAX_WIDTH}}  "
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
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        if self.lang in ("no", "sv"):
            compass_names = [
                "N",
                "NNØ",
                "NØ",
                "ØNØ",
                "Ø",
                "ØSØ",
                "SØ",
                "SSØ",
                "S",
                "SSV",
                "SV",
                "VSV",
                "V",
                "VNV",
                "NV",
                "NNV",
            ]
        elif self.lang == "fi":
            compass_names = [
                "P",
                "PPO",
                "PO",
                "I-PO",
                "I",
                "I-KA",
                "KA",
                "E-KA",
                "E",
                "E-LO",
                "LO",
                "L-LO",
                "L",
                "L-LU",
                "LU",
                "P-LU",
            ]

        arrows = [
            "↓",
            "↙",
            "↙",
            "↙",
            "←",
            "↖",
            "↖",
            "↖",
            "↑",
            "↗",
            "↗",
            "↗",
            "→",
            "↘",
            "↘",
            "↘",
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

        wind_text, wind_arrow = self.degrees_to_wind_direction(
            weather.wind_direction_degrees
        )

        if weather.wind_gust_ms and weather.wind_gust_ms > weather.wind_ms:
            wind_str = f"{weather.wind_ms:.1f} ({weather.wind_gust_ms:.1f}) m/s"
        else:
            wind_str = f"{weather.wind_ms:.1f} m/s"

        degrees_int = round(weather.wind_direction_degrees)

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
        use_normalized_stop_names: bool = DEFAULT_USE_NORMALIZED_STOP_NAMES,
        transport_mode_max_width: int = DEFAULT_TRANSPORT_MODE_MAX_WIDTH,
        transit_naming_style: str = DEFAULT_TRANSIT_NAMING_STYLE,
        mode_overrides: dict[str, str] | None = None,
        system_overrides: dict[str, str] | None = None,
    ):
        self.lang = lang
        self.style = style
        self.terminal_width = terminal_width
        self.use_normalized_stop_names = use_normalized_stop_names
        self.dep_presenter = DeparturePresenter(
            lang=lang,
            style=style,
            mode_max_width=transport_mode_max_width,
            naming_style=transit_naming_style,
            mode_overrides=mode_overrides,
            system_overrides=system_overrides,
        )
        self.weather_presenter = WeatherPresenter(lang=lang, style=style)

    def print_weather_header_msg(self, yr_url, display_name, weather_text) -> None:
        if yr_url and weather_text and self.style == TerminalStyle.MODERN:
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

    def _render_not_found(
        self, state: StopPlaceState, prov_id: str, yellow: str, reset: str
    ) -> bool:
        icon = "❓" if self.style != TerminalStyle.CLASSIC else "[?]"
        err_msg = translate_international_message(
            "stop_not_found", lang=self.lang, id=state.clean_id, provider=prov_id
        )
        print(f" {yellow}{icon} {err_msg}{reset}")
        return True

    def _render_api_error(
        self, state: StopPlaceState, prov_id: str, yellow: str, reset: str
    ) -> bool:
        icon = "⚠️" if self.style != TerminalStyle.CLASSIC else "[!]"
        detalj = (state.error_message or "").split(":", 1)[1]
        print(f" {yellow}{icon} API feil ({prov_id}): {detalj[:80]}{reset}")
        return True

    def _render_offline_warning(
        self, last_updated_iso: str, yellow: str, reset: str
    ) -> bool:
        last_time = arrow.get(last_updated_iso).format("HH:mm:ss")
        icon = "📡" if self.style != TerminalStyle.CLASSIC else "[!]"
        warn_msg = translate_international_message(
            "offline_warn", lang=self.lang, time=last_time
        )
        print(f" {yellow}{icon} {warn_msg}{reset}")
        return False

    def render_error_message(self, state: StopPlaceState, display_name: str) -> bool:
        """
        Renders warning or error details when state.error_message is set.
        Returns True if rendering should stop (fatal error / no cached data),
        or False if cached departure rows can still be shown.
        """
        if not state.error_message:
            return False

        yellow = "\033[93m" if self.style != TerminalStyle.CLASSIC else ""
        reset = "\033[0m" if self.style != TerminalStyle.CLASSIC else ""
        prov_id = getattr(state.provider, "provider_id", str(state.provider))

        if state.error_message.startswith("NOT_FOUND:"):
            return self._render_not_found(state, prov_id, yellow, reset)
        if state.error_message.startswith("API_ERROR:"):
            return self._render_api_error(state, prov_id, yellow, reset)
        if state.normalized_data and state.last_updated_iso:
            return self._render_offline_warning(state.last_updated_iso, yellow, reset)

        icon = "📡" if self.style != TerminalStyle.CLASSIC else "[X]"
        err_msg = translate_international_message(
            "offline_err", lang=self.lang, name=display_name
        )
        print(f" {icon} {err_msg}")
        return True

    def _resolve_display_name(self, state: StopPlaceState) -> str:
        norm = state.normalized_data
        if self.use_normalized_stop_names and norm and norm.name:
            return norm.name
        return state.name

    def _resolve_yr_url(self, norm: NormalizedStopData | None) -> str | None:
        if norm and norm.latitude is not None and norm.longitude is not None:
            return f"https://www.yr.no/nb/værvarsel/daglig-tabell/{norm.latitude:.4f},{norm.longitude:.4f}"
        return None

    def render(self, state: StopPlaceState) -> None:
        has_fresh_data = (
            state.error_message is None and state.normalized_data is not None
        )
        norm = state.normalized_data
        display_name = self._resolve_display_name(state)
        weather_text = self.weather_presenter.format_header(state.weather)
        yr_url = self._resolve_yr_url(norm)

        self.print_weather_header_msg(yr_url, display_name, weather_text)
        if self.render_error_message(state, display_name):
            return

        if not norm:
            print(f"  {translate_international_message('no_data', lang=self.lang)}")
            return
        if not norm.departures:
            print(
                f"  {translate_international_message('no_departures', lang=self.lang)}"
            )
            return

        system_id = state.transit_system_id or detect_transit_system(
            clean_id=state.clean_id,
            latitude=norm.latitude,
            longitude=norm.longitude,
        )

        for dep in norm.departures:
            row = self.dep_presenter.format_departure_row(
                dep, has_fresh_data=has_fresh_data, system_id=system_id
            )
            print(row)
