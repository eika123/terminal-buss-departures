import pytest

from config import (
    load_app_settings,
    load_stop_places,
    resolve_config_and_stops_files,
)


def test_load_app_settings_from_toml(tmp_path):
    toml_file = tmp_path / "custom_config.toml"
    toml_file.write_text("""
[display]
destination_max_width = 35
transport_mode_max_width = 10
transit_naming_style = "original"
terminal_width = 110
language = "sv"

[display.mode_overrides]
metro = "T"

[display.system_overrides]
"oslo_ruter.metro" = "T-banen"

[query]
time_range_seconds = 7200
departures_count = 15
refresh_interval_seconds = 30
""")
    settings = load_app_settings(config_toml_path=toml_file)
    assert settings["destination_max_width"] == 35
    assert settings["transport_mode_max_width"] == 10
    assert settings["transit_naming_style"] == "original"
    assert settings["mode_overrides"]["metro"] == "T"
    assert settings["system_overrides"]["oslo_ruter.metro"] == "T-banen"
    assert settings["terminal_width"] == 110
    assert settings["language"] == "sv"
    assert settings["time_range_seconds"] == 7200
    assert settings["departures_count"] == 15
    assert settings["refresh_interval_seconds"] == 30


def test_load_app_settings_fallback_on_corrupt(tmp_path):
    bad_toml = tmp_path / "broken.toml"
    bad_toml.write_text("invalid [toml content")
    settings = load_app_settings(config_toml_path=bad_toml)
    # Should fall back to built-in defaults without crashing
    assert settings["destination_max_width"] == 28
    assert settings["terminal_width"] == 95


def test_resolve_config_and_stops_explicit():
    env, stops = resolve_config_and_stops_files(custom_env="/tmp/my.env", custom_stops="/tmp/my_stops.txt")
    assert str(env) == "/tmp/my.env"
    assert str(stops) == "/tmp/my_stops.txt"


def test_load_stop_places_valid(tmp_path):
    stops_file = tmp_path / "stoppesteder.txt"
    stops_file.write_text("""
[hjem]
Klimavegen = "NSR:StopPlace:53434"
Jekta = "NSR:StopPlace:52971"

[jobb]
UiT = "NSR:StopPlace:52488"
""")
    profiles = load_stop_places(stops_file)
    assert "hjem" in profiles
    assert "jobb" in profiles
    assert profiles["hjem"].stops["Klimavegen"] == "NSR:StopPlace:53434"
    assert profiles["hjem"].stops["Jekta"] == "NSR:StopPlace:52971"
    assert profiles["jobb"].stops["UiT"] == "NSR:StopPlace:52488"
    assert profiles["hjem"].use_normalized_names is None


def test_load_stop_places_per_profile_options(tmp_path):
    stops_file = tmp_path / "custom_stops.txt"
    stops_file.write_text("""
[hjem, use_normalized_names=false, transit_naming=original]
Min Holdeplass = "NSR:StopPlace:53434"

[jobb, use_normalized_names=true, transit_naming=cultural]
Kontoret = "NSR:StopPlace:52488"
""")
    profiles = load_stop_places(stops_file)
    assert profiles["hjem"].use_normalized_names is False
    assert profiles["hjem"].transit_naming == "original"
    assert profiles["hjem"].options["transit_naming"] == "original"
    assert profiles["hjem"].stops["Min Holdeplass"] == "NSR:StopPlace:53434"
    assert profiles["jobb"].use_normalized_names is True
    assert profiles["jobb"].transit_naming == "cultural"
    assert profiles["jobb"].stops["Kontoret"] == "NSR:StopPlace:52488"


def test_load_stop_places_missing_file(tmp_path):
    missing_file = tmp_path / "nonexistent.txt"
    with pytest.raises(SystemExit):
        load_stop_places(missing_file)


def test_load_stop_places_syntax_error(tmp_path):
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("Klimavegen = NSR:StopPlace:53434\n")  # Missing section header
    with pytest.raises(SystemExit):
        load_stop_places(bad_file)

