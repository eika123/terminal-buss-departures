import pytest

from config import (
    load_app_settings,
    load_stop_places,
    resolve_config_and_stops_files,
)


def test_load_app_settings_from_toml(tmp_path):
    """Verify load_app_settings extracts and validates all table sections in config.toml."""
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
    expected_subset = {
        "destination_max_width": 35,
        "transport_mode_max_width": 10,
        "transit_naming_style": "original",
        "terminal_width": 110,
        "language": "sv",
        "time_range_seconds": 7200,
        "departures_count": 15,
        "refresh_interval_seconds": 30,
        "mode_overrides": {"metro": "T"},
        "system_overrides": {"oslo_ruter.metro": "T-banen"},
    }
    actual_subset = {k: settings.get(k) for k in expected_subset}
    assert actual_subset == expected_subset


def test_load_app_settings_fallback_on_corrupt(tmp_path):
    bad_toml = tmp_path / "broken.toml"
    bad_toml.write_text("invalid [toml content")
    settings = load_app_settings(config_toml_path=bad_toml)
    # Should fall back to built-in defaults without crashing
    assert settings["destination_max_width"] == 28
    assert settings["terminal_width"] == 95


def test_resolve_config_and_stops_explicit():
    env, stops = resolve_config_and_stops_files(
        custom_env="/tmp/my.env", custom_stops="/tmp/my_stops.txt"
    )
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


def test_load_stop_places_empty_section_header(tmp_path):
    """Verify load_stop_places exits when encountering empty section headers e.g. '[]'."""
    bad_file = tmp_path / "empty_header.txt"
    bad_file.write_text("[]\nStop = NSR:123\n")
    with pytest.raises(SystemExit) as exc_info:
        load_stop_places(bad_file)
    assert exc_info.value.code == 1


def test_load_stop_places_section_reopen_and_empty_file(tmp_path):
    """Verify section reopening updates profile options, and completely empty file exits."""
    # Section reopening / options update
    stops_file = tmp_path / "multi_header.txt"
    stops_file.write_text("""
[hjem, use_normalized_names=false]
Stop1 = "123"

[hjem, transit_naming=original]
Stop2 = "456"
""")
    profiles = load_stop_places(stops_file)
    assert profiles["hjem"].use_normalized_names is False
    assert profiles["hjem"].transit_naming == "original"
    assert len(profiles["hjem"].stops) == 2

    # Completely empty file
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("# only comments\n\n")
    with pytest.raises(SystemExit) as exc_info:
        load_stop_places(empty_file)
    assert exc_info.value.code == 1


def test_resolve_config_and_stops_files_xdg_and_cwd(tmp_path, monkeypatch):
    """Verify resolve_config_and_stops_files falls back to XDG config dir when not in local dev."""
    # Point XDG_CONFIG_HOME to tmp_path
    xdg_dir = tmp_path / "avgangstider"
    xdg_dir.mkdir()
    xdg_env = xdg_dir / ".env"
    xdg_env.write_text("ET_CLIENT_NAME=xdg_test\n")
    xdg_stops = xdg_dir / "stoppesteder.txt"
    xdg_stops.write_text("[hjem]\nStop = 1\n")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # Non-repo directory

    env, stops = resolve_config_and_stops_files()
    assert env == xdg_env
    assert stops == xdg_stops
