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
    p_no = DeparturePresenter(lang="no")
    assert "Trikk" in p_no.format_transport_mode("tram")
    assert "Buss" in p_no.format_transport_mode("bus")

    p_fi = DeparturePresenter(lang="fi")
    assert "Spora" in p_fi.format_transport_mode("tram")
    assert "Bussi" in p_fi.format_transport_mode("bus")


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

