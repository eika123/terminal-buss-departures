import pytest
from dotenv import dotenv_values


def _scrub_response_cookies(response: dict) -> dict:
    """Strip Set-Cookie from recorded response headers to avoid saving session cookies."""
    headers = response.get("headers", {})
    headers.pop("Set-Cookie", None)
    headers.pop("set-cookie", None)
    return response


@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration: scrubs secrets, strips cookies, and normalizes cassettes."""
    return {
        # Scrub credentials and cookies from request headers
        "filter_headers": [
            ("ET-Client-Name", "DUMMY_ET_CLIENT_NAME"),
            ("digitransit-subscription-key", "DUMMY_DIGITRANSIT_KEY"),
            ("User-Agent", "DUMMY_USER_AGENT"),
            ("Cookie", None),
        ],
        # Strip Set-Cookie response headers before recording to disk
        "before_record_response": _scrub_response_cookies,
        # Re-record cassette automatically if older than 7 days (7 * 24 * 3600 seconds)
        "re_record_interval": 604800,
        "decode_compressed_response": True,
    }


@pytest.fixture(scope="module")
def live_or_dummy_app_config():
    """
    Loads real credentials from .env if recording, or returns dummy values
    so tests can replay recorded cassettes in isolated/offline environments.
    """
    cfg = dotenv_values(".env")
    return {
        "ET_CLIENT_NAME": cfg.get("ET_CLIENT_NAME") or "test-avgangstider-client",
        "MET_USER_AGENT": cfg.get("MET_USER_AGENT") or "TestTransitApp/1.0 (contact: test@example.com)",
        "DIGITRANSIT_SUBSCRIPTION_KEY": cfg.get("DIGITRANSIT_SUBSCRIPTION_KEY") or "dummy_digitransit_sub_key",
    }
