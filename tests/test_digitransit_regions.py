import pytest

from adapters import detect_provider
from adapters.digitransit import DIGITRANSIT_FEED_ALIASES, _resolve_digitransit_ids


@pytest.mark.parametrize(
    ("raw_id", "expected_provider", "expected_id1"),
    [
        ("fi:hsl:1020455", "digitransit_hsl", "1020455"),
        ("fi:HSL:1020455", "digitransit_hsl", "1020455"),
        ("fi:hki:1040101", "digitransit_hsl", "1040101"),
        ("hsl:1020455", "digitransit_hsl", "1020455"),
        ("tampere:0805", "digitransit_finland", "tampere:0805"),
        ("fi:Turku:148", "digitransit_finland", "FOLI:148"),
        ("fi:OULU:1234", "digitransit_finland", "OULU:1234"),
        *[
            (f"fi:{alias}:1234", "digitransit_finland", f"{feed}:1234")
            for alias, feed in sorted(DIGITRANSIT_FEED_ALIASES.items())
        ],
        ("fi:CAR_FERRIES:999", "digitransit_finland", "CAR_FERRIES:999"),
    ],
)
def test_digitransit_regions_routing_and_resolution(
    raw_id: str, expected_provider: str, expected_id1: str
) -> None:
    """All Finnish Digitransit regions route to the right provider and feed ID."""
    provider, clean_id = detect_provider(raw_id)
    assert provider == expected_provider
    id1, _ = _resolve_digitransit_ids(clean_id)
    assert id1 == expected_id1


def test_digitransit_bare_id_raises() -> None:
    """Bare IDs without a feed prefix must fail loudly."""
    provider, clean_id = detect_provider("fi:1492141")
    assert provider == "digitransit_finland"
    with pytest.raises(ValueError, match="must include a feed prefix"):
        _resolve_digitransit_ids(clean_id)
