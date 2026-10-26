import pytest

from adapters.entur import default_entur_provider
from models import DepartureData, NormalizedStopData, StopPlaceState
from presenters import DeparturePresenter, StopPlacePresenter
from transit_identities import (
    detect_transit_system,
    resolve_transit_term,
)


def test_detect_transit_system_by_prefix():
    assert detect_transit_system(clean_id="HSL:1020455") == "helsinki_hsl"
    assert detect_transit_system(clean_id="fi:hsl:1020455") == "helsinki_hsl"
    assert detect_transit_system(clean_id="hki:12345") == "helsinki_hsl"
    assert detect_transit_system(clean_id="tampere:001") == "tampere_nysse"
    assert detect_transit_system(clean_id="nysse:0805") == "tampere_nysse"
    assert detect_transit_system(clean_id="fi:nysse:0805") == "tampere_nysse"
    assert detect_transit_system(clean_id="SL:9112") == "stockholm_sl"
    assert detect_transit_system(clean_id="TFL:9400ZZLUBST") == "london_tfl"
    assert (
        detect_transit_system(clean_id="NSR:StopPlace:58366") is None
    )  # Resolved by coordinates


def test_detect_transit_system_by_coordinates():
    # Oslo S coordinates
    assert detect_transit_system(latitude=59.911, longitude=10.753) == "oslo_ruter"
    # Bergen Byparken coordinates
    assert detect_transit_system(latitude=60.391, longitude=5.324) == "bergen_skyss"
    # Trondheim Torvet coordinates
    assert detect_transit_system(latitude=63.430, longitude=10.395) == "trondheim_atb"
    # Helsinki Kamppi coordinates
    assert detect_transit_system(latitude=60.169, longitude=24.933) == "helsinki_hsl"
    # Tampere Keskustori coordinates
    assert detect_transit_system(latitude=61.498, longitude=23.761) == "tampere_nysse"
    # Stockholm T-Centralen coordinates
    assert detect_transit_system(latitude=59.331, longitude=18.061) == "stockholm_sl"
    # London Westminster coordinates
    assert detect_transit_system(latitude=51.501, longitude=-0.125) == "london_tfl"
    # Berlin Alexanderplatz coordinates
    assert detect_transit_system(latitude=52.521, longitude=13.411) == "berlin_bvg"
    # Unknown remote location (e.g. Alta, Finnmark)
    assert detect_transit_system(latitude=69.968, longitude=23.271) is None


@pytest.mark.parametrize(
    "mode,system_id,user_lang,expected_term",
    [
        # Oslo T-bane
        ("metro", "oslo_ruter", "no", "T-bane"),
        ("metro", "oslo_ruter", "sv", "T-bana"),
        ("metro", "oslo_ruter", "fi", "Metro"),
        ("metro", "oslo_ruter", "en", "T-bane"),
        # Bergen Bybanen
        ("tram", "bergen_skyss", "no", "Bybanen"),
        ("tram", "bergen_skyss", "fi", "Pikaspora"),
        ("tram", "bergen_skyss", "sv", "Bybanan"),
        # Tampere Nysse / Ratikka
        ("tram", "tampere_nysse", "fi", "Ratikka"),
        ("tram", "tampere_nysse", "no", "Trikk"),
        ("tram", "tampere_ratikka", "fi", "Ratikka"),
        ("tram", "tampere_ratikka", "no", "Trikk"),
        # London Tube
        ("metro", "london_tfl", "en", "Tube"),
        ("metro", "london_tfl", "no", "Tuben"),
        ("metro", "london_tfl", "sv", "Tuben"),
        ("metro", "london_tfl", "fi", "Metro"),
        # Berlin U-Bahn
        ("metro", "berlin_bvg", "en", "U-Bahn"),
        ("metro", "berlin_bvg", "fi", "Metro"),
    ],
)
def test_resolve_transit_term_cultural_exonyms(
    mode: str, system_id: str, user_lang: str, expected_term: str
):
    """Verify cultural transit naming style returns authentic exonyms per user language."""
    assert (
        resolve_transit_term(
            mode, system_id, user_lang=user_lang, naming_style="cultural"
        )
        == expected_term
    )


@pytest.mark.parametrize(
    "mode,system_id,user_lang,expected_term",
    [
        ("metro", "oslo_ruter", "fi", "T-bane"),
        ("metro", "london_tfl", "no", "Tube"),
        ("metro", "berlin_bvg", "no", "U-Bahn"),
        ("tram", "bergen_skyss", "fi", "Bybanen"),
        ("tram", "tampere_ratikka", "sv", "Ratikka"),
    ],
)
def test_resolve_transit_term_original_mode(
    mode: str, system_id: str, user_lang: str, expected_term: str
):
    """Verify original transit naming style yields native endonyms regardless of user language."""
    assert (
        resolve_transit_term(
            mode, system_id, user_lang=user_lang, naming_style="original"
        )
        == expected_term
    )


def test_resolve_transit_term_edge_cases():
    """Verify handling of unknown transit systems, invalid languages, and missing dictionary terms."""
    # Unknown transit system falls back to international message translation
    assert (
        resolve_transit_term("metro", "non_existent_system", user_lang="no") == "T-bane"
    )

    # Unsupported user language code falls back to English exonym
    assert (
        resolve_transit_term("metro", "london_tfl", user_lang="invalid_lang") == "Tube"
    )

    # Mode not recognized in registry or dictionary falls back to capitalized mode name
    assert resolve_transit_term("teleport", "oslo_ruter", user_lang="en") == "Teleport"


def test_resolve_transit_term_generic_mode():
    # Standard dictionary translations
    assert (
        resolve_transit_term(
            "metro", "oslo_ruter", user_lang="no", naming_style="generic"
        )
        == "T-bane"
    )
    assert (
        resolve_transit_term(
            "metro", "london_tfl", user_lang="no", naming_style="generic"
        )
        == "T-bane"
    )
    assert (
        resolve_transit_term(
            "metro", "london_tfl", user_lang="fi", naming_style="generic"
        )
        == "Metro"
    )


def test_resolve_transit_term_overrides():
    # Mode override overrides all systems
    mode_ov = {"metro": "T"}
    assert (
        resolve_transit_term(
            "metro", "helsinki_hsl", user_lang="fi", mode_overrides=mode_ov
        )
        == "T"
    )

    # System-specific override overrides specific system
    sys_ov = {"oslo_ruter.metro": "T", "helsinki_hsl.metro": "M"}
    assert (
        resolve_transit_term(
            "metro", "oslo_ruter", user_lang="no", system_overrides=sys_ov
        )
        == "T"
    )
    assert (
        resolve_transit_term(
            "metro", "helsinki_hsl", user_lang="fi", system_overrides=sys_ov
        )
        == "M"
    )
    # Unaffected system falls back to cultural
    assert (
        resolve_transit_term(
            "metro", "london_tfl", user_lang="en", system_overrides=sys_ov
        )
        == "Tube"
    )


def test_departure_presenter_with_transit_identities():
    dep = DepartureData(
        line_code="1",
        transport_mode="metro",
        destination="Frognerseteren",
        aimed_iso="2026-10-25T12:00:00+02:00",
        expected_iso="2026-10-25T12:02:00+02:00",
        is_realtime=True,
    )

    # Norwegian in Oslo: "T-bane"
    p_no = DeparturePresenter(lang="no", naming_style="cultural", mode_max_width=7)
    row_no = p_no.format_departure_row(dep, has_fresh_data=True, system_id="oslo_ruter")
    assert "T-bane" in row_no

    # Finn in Oslo: "Metro"
    p_fi = DeparturePresenter(lang="fi", naming_style="cultural", mode_max_width=7)
    row_fi = p_fi.format_departure_row(dep, has_fresh_data=True, system_id="oslo_ruter")
    assert "Metro" in row_fi

    # Finn in Oslo with original mode: "T-bane"
    p_fi_orig = DeparturePresenter(lang="fi", naming_style="original", mode_max_width=7)
    row_fi_orig = p_fi_orig.format_departure_row(
        dep, has_fresh_data=True, system_id="oslo_ruter"
    )
    assert "T-bane" in row_fi_orig


def test_stop_place_presenter_automatic_detection(capsys):
    norm = NormalizedStopData(
        name="Jernbanetorget",
        latitude=59.911,
        longitude=10.753,
        departures=[
            DepartureData(
                line_code="5",
                transport_mode="metro",
                destination="Ringen",
                aimed_iso="2026-10-25T12:00:00+02:00",
                expected_iso="2026-10-25T12:00:00+02:00",
                is_realtime=True,
            )
        ],
    )
    state = StopPlaceState(
        name="Jernbanetorget",
        raw_id="NSR:StopPlace:58366",
        clean_id="NSR:StopPlace:58366",
        provider=default_entur_provider,
        normalized_data=norm,
    )

    # Render for a Finnish user: should automatically detect Oslo coordinates and render Metro
    presenter = StopPlacePresenter(
        lang="fi", transit_naming_style="cultural", transport_mode_max_width=7
    )
    presenter.render(state)

    captured = capsys.readouterr().out
    assert "Metro" in captured
