"""Unit tests for cli.py command-line interface helper routines and profile resolution."""

import argparse
import sys
from pathlib import Path

import pytest

from cli import (
    _ensure_config_file,
    _extract_flag_value,
    _initialize_stops_state,
    _parse_early_cli_options,
    _resolve_active_language,
    _resolve_display_preferences,
    _select_active_profile,
    clear_terminal,
    parse_arguments,
)
from config import DEFAULT_TRANSIT_NAMING_STYLE, DEFAULT_USE_NORMALIZED_STOP_NAMES
from models import StopProfile


class TestCliArgumentParsing:
    """Tests for CLI flag extraction and early argument parsing."""

    @pytest.mark.parametrize(
        "argv,flag,expected",
        [
            (["cmd", "--config", "/tmp/test.env"], "--config", "/tmp/test.env"),
            (["cmd", "--config=/tmp/test.env"], "--config", "/tmp/test.env"),
            (["cmd", "--stops", "/tmp/stops.txt"], "--stops", "/tmp/stops.txt"),
            (["cmd", "--other", "val"], "--config", None),
            (["cmd", "--config"], "--config", None),
        ],
    )
    def test_extract_flag_value_variations(self, argv: list[str], flag: str, expected: str | None):
        """Verify _extract_flag_value correctly parses both space-separated and equals-separated values."""
        assert _extract_flag_value(argv, flag) == expected

    def test_parse_early_cli_options_valid(self):
        """Verify _parse_early_cli_options correctly identifies custom configs and recognized languages."""
        argv = ["app", "--config", "custom.env", "--stops=/tmp/my_stops.txt", "--lang=fi"]
        env, stops, lang = _parse_early_cli_options(argv)
        assert env == "custom.env"
        assert stops == "/tmp/my_stops.txt"
        assert lang == "fi"

    def test_parse_early_cli_options_ignores_unknown_language(self):
        """Verify _parse_early_cli_options rejects invalid language codes during early parsing."""
        argv = ["app", "--lang=de"]
        _, _, lang = _parse_early_cli_options(argv)
        assert lang is None

    def test_parse_arguments_full_flags(self):
        """Verify parse_arguments correctly maps numerical and string flags."""
        profiles = {
            "home": StopProfile(name="home", stops={"Hjemme": "NSR:StopPlace:1"}),
            "work": StopProfile(name="work", stops={"Jobb": "NSR:StopPlace:2"}),
        }
        args = parse_arguments(
            profiles,
            argv=["--antall", "15", "--timerange", "7200", "--intervall", "30", "--work"],
        )
        assert isinstance(args, argparse.Namespace)
        assert args.antall == 15
        assert args.timerange == 7200
        assert args.intervall == 30
        assert args.profile == "work"


class TestCliLanguageAndConfigResolution:
    """Tests for configuration file validation and active language determination."""

    def test_resolve_active_language_from_cli(self, tmp_path: Path):
        """Verify early CLI flag takes precedence over configuration file settings."""
        dummy_env = tmp_path / ".env"
        dummy_env.write_text("LANGUAGE=sv\n", encoding="utf-8")
        assert _resolve_active_language(cli_lang="fi", env_path=dummy_env) == "fi"

    def test_resolve_active_language_from_env_file(self, tmp_path: Path):
        """Verify .env setting is used when no CLI language flag is passed."""
        dummy_env = tmp_path / ".env"
        dummy_env.write_text("LANGUAGE=sv\n", encoding="utf-8")
        assert _resolve_active_language(cli_lang=None, env_path=dummy_env) == "sv"

    def test_resolve_active_language_fallback_to_default(self, tmp_path: Path):
        """Verify fallback to default language when .env contains invalid language code."""
        dummy_env = tmp_path / ".env"
        dummy_env.write_text("LANGUAGE=unsupported_lang\n", encoding="utf-8")
        assert _resolve_active_language(cli_lang=None, env_path=dummy_env) == "no"

    def test_ensure_config_file_success(self, tmp_path: Path):
        """Verify _ensure_config_file succeeds when .env file exists."""
        dummy_env = tmp_path / ".env"
        dummy_env.write_text("ET_CLIENT_NAME=tester\n", encoding="utf-8")
        # Should not raise or exit
        _ensure_config_file(dummy_env, "no")

    def test_ensure_config_file_missing_exits(self, tmp_path: Path):
        """Verify _ensure_config_file terminates the program when .env is absent."""
        missing_env = tmp_path / "non_existent.env"
        with pytest.raises(SystemExit) as exc_info:
            _ensure_config_file(missing_env, "no")
        assert exc_info.value.code == 1


class TestCliProfileAndStateSetup:
    """Tests for profile selection, stop place state mapping, and presentation preference resolution."""

    def test_select_active_profile_explicit_flag(self):
        """Verify selecting a profile via named flag e.g. args.profile."""
        home_profile = StopProfile(name="home", stops={"Stop1": "123"})
        work_profile = StopProfile(name="work", stops={"Stop2": "456"})
        all_profiles = {"home": home_profile, "work": work_profile}

        args = argparse.Namespace(profile="work", positional_profile=None)
        selected = _select_active_profile(all_profiles, args, "no")
        assert selected.name == "work"

    def test_select_active_profile_positional_arg(self):
        """Verify selecting a profile via positional argument e.g. 'avgangstider work'."""
        home_profile = StopProfile(name="home", stops={"Stop1": "123"})
        work_profile = StopProfile(name="work", stops={"Stop2": "456"})
        all_profiles = {"home": home_profile, "work": work_profile}

        args = argparse.Namespace(profile=None, positional_profile="Work")
        selected = _select_active_profile(all_profiles, args, "no")
        assert selected.name == "work"

    def test_select_active_profile_defaults_to_first(self):
        """Verify default selection selects the first declared profile section when no flag is given."""
        home_profile = StopProfile(name="home", stops={"Stop1": "123"})
        work_profile = StopProfile(name="work", stops={"Stop2": "456"})
        all_profiles = {"home": home_profile, "work": work_profile}

        args = argparse.Namespace(profile=None, positional_profile=None)
        selected = _select_active_profile(all_profiles, args, "no")
        assert selected.name == "home"

    def test_select_active_profile_unknown_exits(self):
        """Verify selecting a non-existent profile terminates with error message."""
        home_profile = StopProfile(name="home", stops={"Stop1": "123"})
        all_profiles = {"home": home_profile}

        args = argparse.Namespace(profile="vacation", positional_profile=None)
        with pytest.raises(SystemExit) as exc_info:
            _select_active_profile(all_profiles, args, "no")
        assert exc_info.value.code == 1

    def test_select_active_profile_empty_stops_exits(self):
        """Verify selecting a profile with zero stops prints error and exits."""
        empty_profile = StopProfile(name="empty", stops={})
        all_profiles = {"empty": empty_profile}

        args = argparse.Namespace(profile="empty", positional_profile=None)
        with pytest.raises(SystemExit) as exc_info:
            _select_active_profile(all_profiles, args, "no")
        assert exc_info.value.code == 1

    def test_initialize_stops_state(self):
        """Verify _initialize_stops_state instantiates StopPlaceState with detected provider."""
        stops = {
            "Jernbanetorget": "NSR:StopPlace:58366",
            "Kamppi": "HSL:1020455",
        }
        states = _initialize_stops_state(stops)
        assert len(states) == 2
        assert states["Jernbanetorget"].provider.provider_id == "entur"
        assert states["Kamppi"].provider.provider_id == "digitransit_hsl"

    def test_resolve_display_preferences_profile_override(self):
        """Verify per-profile option takes precedence over global settings."""
        profile = StopProfile(
            name="test",
            stops={"S": "1"},
            use_normalized_names=False,
            transit_naming="original",
        )
        app_config = {
            "use_normalized_stop_names": "true",
            "transit_naming_style": "cultural",
        }
        use_norm, transit_naming = _resolve_display_preferences(profile, app_config)
        assert use_norm is False
        assert transit_naming == "original"

    def test_resolve_display_preferences_global_fallback(self):
        """Verify global settings are used when per-profile options are None."""
        profile = StopProfile(name="test", stops={"S": "1"})
        app_config = {
            "use_normalized_stop_names": "true",
            "transit_naming_style": "cultural",
        }
        use_norm, transit_naming = _resolve_display_preferences(profile, app_config)
        assert use_norm is True
        assert transit_naming == "cultural"

    def test_resolve_display_preferences_default_fallback(self):
        """Verify built-in defaults are used when neither profile nor app_config specifies settings."""
        profile = StopProfile(name="test", stops={"S": "1"})
        use_norm, transit_naming = _resolve_display_preferences(profile, {})
        assert use_norm == DEFAULT_USE_NORMALIZED_STOP_NAMES
        assert transit_naming == DEFAULT_TRANSIT_NAMING_STYLE


def test_clear_terminal(mocker):
    """Verify clear_terminal invokes the platform-appropriate terminal clearing command."""
    mock_run = mocker.patch("subprocess.run")
    clear_terminal()
    expected_cmd = "cls" if sys.platform.startswith("win") else "clear"
    mock_run.assert_called_once_with([expected_cmd], check=True)
