import arrow

from adapters.entur import default_entur_provider
from models import DepartureData, NormalizedStopData, StopPlaceState, WeatherData
from presenters import (
    DeparturePresenter,
    StopPlacePresenter,
    WeatherPresenter,
    make_terminal_hyperlink,
)


def test_make_terminal_hyperlink():
    link = make_terminal_hyperlink("https://example.com", "ClickMe")
    assert "https://example.com" in link
    assert "ClickMe" in link
    assert link.startswith("\033]8;;")


def test_departure_presenter_transport_mode_translations():
    p_no = DeparturePresenter(lang="no", mode_max_width=7)
    assert "Trikk" in p_no.format_transport_mode("tram")
    assert "Buss" in p_no.format_transport_mode("bus")

    p_fi = DeparturePresenter(lang="fi", mode_max_width=7)
    assert "Spora" in p_fi.format_transport_mode("tram")
    assert "Bussi" in p_fi.format_transport_mode("bus")

    # Swedish with width 7: Spårvagn truncates to Spårv., T-bana fits within 7
    p_sv = DeparturePresenter(lang="sv", mode_max_width=7)
    assert "Spårv." in p_sv.format_transport_mode("tram")
    assert "T-bana" in p_sv.format_transport_mode("metro")

    # Swedish with width 10: Spårvagn is displayed without truncation
    p_sv_10 = DeparturePresenter(lang="sv", mode_max_width=10)
    assert "Spårvagn" in p_sv_10.format_transport_mode("tram")

    # Generic truncation and natural abbreviation for long names
    p_custom = DeparturePresenter(lang="no", mode_max_width=5)
    # Trikk (5) fits exactly in 5
    assert "Trikk" in p_custom.format_transport_mode("tram")
    # Custom long word truncated with dot (4 chars + dot = 5 chars)
    assert "Fant." in p_custom.format_transport_mode("fantasi_transport")


def test_departure_presenter_format_delay():
    p = DeparturePresenter(lang="no")
    # On time
    assert "I rute" in p.format_delay("2026-10-25T12:00:00+02:00", "2026-10-25T12:00:00+02:00")
    # Delayed
    assert "forsinket" in p.format_delay("2026-10-25T12:00:00+02:00", "2026-10-25T12:05:00+02:00")
    # Early
    assert "tidlig" in p.format_delay("2026-10-25T12:05:00+02:00", "2026-10-25T12:00:00+02:00")


def test_departure_presenter_format_departure_row_realtime():
    p = DeparturePresenter(lang="no")
    now_iso = arrow.now().shift(minutes=+5).isoformat()
    dep = DepartureData(
        line_code="28",
        transport_mode="bus",
        destination="Hamna",
        aimed_iso=now_iso,
        expected_iso=now_iso,
        is_realtime=True,
    )
    row = p.format_departure_row(dep, has_fresh_data=True)
    assert "28" in row
    assert "Hamna" in row
    assert "I rute" in row


def test_departure_presenter_format_departure_row_offline():
    p = DeparturePresenter(lang="no")
    now_iso = arrow.now().shift(minutes=+5).isoformat()
    dep = DepartureData(
        line_code="28",
        transport_mode="bus",
        destination="Hamna",
        aimed_iso=now_iso,
        expected_iso=now_iso,
        is_realtime=True,
    )
    row = p.format_departure_row(dep, has_fresh_data=False)
    assert "frakoblet" in row


def test_weather_presenter_header_no_and_fi():
    weather = WeatherData(
        temperature_c=10.0,
        wind_ms=6.4,
        wind_gust_ms=9.1,
        wind_direction_degrees=166.0,
        symbol_code="cloudy",
        fetched_at_iso="2026-10-25T12:00:00+00:00",
    )

    p_no = WeatherPresenter(lang="no")
    hdr_no = p_no.format_header(weather)
    assert "Skyet" in hdr_no
    assert "SSØ" in hdr_no
    assert "10°C" in hdr_no

    p_fi = WeatherPresenter(lang="fi")
    hdr_fi = p_fi.format_header(weather)
    assert "Pilvistä" in hdr_fi
    assert "E-KA" in hdr_fi
    assert "10°C" in hdr_fi


def test_stop_place_presenter_render_normal(capsys):
    pres = StopPlacePresenter(lang="no")
    dep = DepartureData(
        line_code="28",
        transport_mode="bus",
        destination="Sentrum",
        aimed_iso=arrow.now().shift(minutes=+10).isoformat(),
        expected_iso=arrow.now().shift(minutes=+10).isoformat(),
        is_realtime=True,
    )
    norm = NormalizedStopData(name="Klimavegen", latitude=69.65, longitude=18.95, departures=[dep])
    state = StopPlaceState(
        name="Klimavegen",
        raw_id="NSR:StopPlace:53434",
        clean_id="NSR:StopPlace:53434",
        provider=default_entur_provider,
        normalized_data=norm,
    )

    pres.render(state)
    captured = capsys.readouterr()
    assert "Klimavegen" in captured.out
    assert "Sentrum" in captured.out
    assert "28" in captured.out


def test_stop_place_presenter_render_error(capsys):
    pres = StopPlacePresenter(lang="no")
    state = StopPlaceState(
        name="Ukjent Stopp",
        raw_id="NSR:StopPlace:99999",
        clean_id="NSR:StopPlace:99999",
        provider=default_entur_provider,
        error_message="NOT_FOUND:Stop not found",
    )

    pres.render(state)
    captured = capsys.readouterr()
    assert "Fant ikke stoppested" in captured.out


def test_stop_place_presenter_user_vs_normalized_name(capsys):
    dep = DepartureData(
        line_code="500",
        transport_mode="bus",
        destination="Itäkeskus",
        aimed_iso=arrow.now().shift(minutes=+5).isoformat(),
        expected_iso=arrow.now().shift(minutes=+5).isoformat(),
        is_realtime=True,
    )
    norm = NormalizedStopData(name="Itäkeskus (M)", latitude=60.2, longitude=25.0, departures=[dep])
    state = StopPlaceState(
        name="Hjemme - Østgående",
        raw_id="HSL:1020455",
        clean_id="1020455",
        provider=default_entur_provider,
        normalized_data=norm,
    )

    # 1. When use_normalized_stop_names=True, official API name is shown
    pres_norm = StopPlacePresenter(lang="no", use_normalized_stop_names=True)
    pres_norm.render(state)
    out_norm = capsys.readouterr().out
    assert "Itäkeskus (M)" in out_norm
    assert "Hjemme - Østgående" not in out_norm

    # 2. When use_normalized_stop_names=False, user configured alias is preserved
    pres_user = StopPlacePresenter(lang="no", use_normalized_stop_names=False)
    pres_user.render(state)
    out_user = capsys.readouterr().out
    assert "Hjemme - Østgående" in out_user
    assert "Itäkeskus (M)" not in out_user


def test_presenter_classic_style_and_truncation(capsys):
    """Verify classic terminal style without ANSI escapes and specific mode abbreviations."""
    from config import TerminalStyle

    # Mode abbreviation: Tunnelbana -> Tunn. when width is 5
    pres_classic = DeparturePresenter(lang="sv", mode_max_width=5, style=TerminalStyle.CLASSIC)
    assert pres_classic.format_transport_mode("Tunnelbana") == "Tunn."

    # Delay formatting in classic mode
    now_iso = arrow.now().isoformat()
    delayed_iso = arrow.now().shift(minutes=+3).isoformat()
    delay_str = pres_classic.format_delay(now_iso, delayed_iso)
    assert "[!]" in delay_str
    assert "forsinket" in delay_str or "försenad" in delay_str or "delayed" in delay_str

    early_iso = arrow.now().shift(minutes=-2).isoformat()
    early_str = pres_classic.format_delay(now_iso, early_iso)
    assert "[+]" in early_str

    on_time_str = pres_classic.format_delay(now_iso, now_iso)
    assert "[V]" in on_time_str


def test_stop_place_presenter_api_error_and_empty_departures(capsys):
    """Verify presentation of API error banners, empty departure lists, and missing data."""
    from config import TerminalStyle

    pres = StopPlacePresenter(lang="no", style=TerminalStyle.CLASSIC)

    # 1. API error banner
    api_err_state = StopPlaceState(
        name="Oslo S",
        raw_id="NSR:StopPlace:58366",
        clean_id="NSR:StopPlace:58366",
        provider=default_entur_provider,
        error_message="API_ERROR:Upstream service timeout",
    )
    pres.render(api_err_state)
    out = capsys.readouterr().out
    assert "API feil" in out
    assert "Upstream service timeout" in out

    # 2. Missing normalized data
    no_data_state = StopPlaceState(
        name="Oslo S",
        raw_id="NSR:StopPlace:58366",
        clean_id="NSR:StopPlace:58366",
        provider=default_entur_provider,
        normalized_data=None,
    )
    pres.render(no_data_state)
    out = capsys.readouterr().out
    assert "Ingen data tilgjengelig" in out

    # 3. Empty departures
    empty_deps_state = StopPlaceState(
        name="Oslo S",
        raw_id="NSR:StopPlace:58366",
        clean_id="NSR:StopPlace:58366",
        provider=default_entur_provider,
        normalized_data=NormalizedStopData(name="Oslo S", latitude=59.91, longitude=10.75, departures=[]),
    )
    pres.render(empty_deps_state)
    out = capsys.readouterr().out
    assert "Ingen planlagte avganger" in out


