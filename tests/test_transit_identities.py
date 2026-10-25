from adapters.entur import default_entur_provider
from models import DepartureData, NormalizedStopData, StopPlaceState
from presenters import DeparturePresenter, StopPlacePresenter
from transit_identities import (
    detect_transit_system,
    resolve_transit_term,
)


def test_detect_transit_system_by_prefix():
    assert detect_transit_system(clean_id="HSL:1020455") == "helsinki_hsl"
    assert detect_transit_system(clean_id="hki:12345") == "helsinki_hsl"
    assert detect_transit_system(clean_id="tampere:001") == "tampere_ratikka"
    assert detect_transit_system(clean_id="SL:9112") == "stockholm_sl"
    assert detect_transit_system(clean_id="TFL:9400ZZLUBST") == "london_tfl"
    assert detect_transit_system(clean_id="NSR:StopPlace:58366") is None  # Resolved by coordinates


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
    assert detect_transit_system(latitude=61.498, longitude=23.761) == "tampere_ratikka"
    # Stockholm T-Centralen coordinates
    assert detect_transit_system(latitude=59.331, longitude=18.061) == "stockholm_sl"
    # London Westminster coordinates
    assert detect_transit_system(latitude=51.501, longitude=-0.125) == "london_tfl"
    # Berlin Alexanderplatz coordinates
    assert detect_transit_system(latitude=52.521, longitude=13.411) == "berlin_bvg"
    # Unknown remote location (e.g. Alta, Finnmark)
    assert detect_transit_system(latitude=69.968, longitude=23.271) is None


def test_resolve_transit_term_cultural_exonyms():
    # Oslo T-bane
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="no", naming_style="cultural") == "T-bane"
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="sv", naming_style="cultural") == "T-bana"
    # Crucial cultural touch: Finnish visitors refer to Oslo's T-bane as "Metro"
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="fi", naming_style="cultural") == "Metro"
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="en", naming_style="cultural") == "T-bane"

    # Bergen Bybanen: Finns colloquially say "Pikaspora" (express/light tram)
    assert resolve_transit_term("tram", "bergen_skyss", user_lang="no", naming_style="cultural") == "Bybanen"
    assert resolve_transit_term("tram", "bergen_skyss", user_lang="fi", naming_style="cultural") == "Pikaspora"
    assert resolve_transit_term("tram", "bergen_skyss", user_lang="sv", naming_style="cultural") == "Bybanan"

    # Tampere Ratikka
    assert resolve_transit_term("tram", "tampere_ratikka", user_lang="fi", naming_style="cultural") == "Ratikka"
    assert resolve_transit_term("tram", "tampere_ratikka", user_lang="no", naming_style="cultural") == "Trikk"

    # London Tube
    assert resolve_transit_term("metro", "london_tfl", user_lang="en", naming_style="cultural") == "Tube"
    assert resolve_transit_term("metro", "london_tfl", user_lang="no", naming_style="cultural") == "Tuben"
    assert resolve_transit_term("metro", "london_tfl", user_lang="sv", naming_style="cultural") == "Tuben"
    assert resolve_transit_term("metro", "london_tfl", user_lang="fi", naming_style="cultural") == "Metro"


def test_resolve_transit_term_original_mode():
    # Authentic local endonyms regardless of user language
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="fi", naming_style="original") == "T-bane"
    assert resolve_transit_term("metro", "london_tfl", user_lang="no", naming_style="original") == "Tube"
    assert resolve_transit_term("metro", "berlin_bvg", user_lang="no", naming_style="original") == "U-Bahn"
    assert resolve_transit_term("tram", "bergen_skyss", user_lang="fi", naming_style="original") == "Bybanen"
    assert resolve_transit_term("tram", "tampere_ratikka", user_lang="sv", naming_style="original") == "Ratikka"


def test_resolve_transit_term_generic_mode():
    # Standard dictionary translations
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="no", naming_style="generic") == "T-bane"
    assert resolve_transit_term("metro", "london_tfl", user_lang="no", naming_style="generic") == "T-bane"
    assert resolve_transit_term("metro", "london_tfl", user_lang="fi", naming_style="generic") == "Metro"


def test_resolve_transit_term_overrides():
    # Mode override overrides all systems
    mode_ov = {"metro": "T"}
    assert resolve_transit_term("metro", "helsinki_hsl", user_lang="fi", mode_overrides=mode_ov) == "T"

    # System-specific override overrides specific system
    sys_ov = {"oslo_ruter.metro": "T", "helsinki_hsl.metro": "M"}
    assert resolve_transit_term("metro", "oslo_ruter", user_lang="no", system_overrides=sys_ov) == "T"
    assert resolve_transit_term("metro", "helsinki_hsl", user_lang="fi", system_overrides=sys_ov) == "M"
    # Unaffected system falls back to cultural
    assert resolve_transit_term("metro", "london_tfl", user_lang="en", system_overrides=sys_ov) == "Tube"


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
    row_fi_orig = p_fi_orig.format_departure_row(dep, has_fresh_data=True, system_id="oslo_ruter")
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
    presenter = StopPlacePresenter(lang="fi", transit_naming_style="cultural", transport_mode_max_width=7)
    presenter.render(state)

    captured = capsys.readouterr().out
    assert "Metro" in captured
