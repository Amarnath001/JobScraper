import pytest

from app.services.location_filter_service import (
    LocationCategory,
    classify_location,
    is_us_or_remote,
    normalize_location,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  San Francisco,  CA  ", "san francisco, ca"),
        ("Remote\tUS", "remote us"),
        ("", ""),
    ],
)
def test_normalize_location(raw: str, expected: str) -> None:
    assert normalize_location(raw) == expected


@pytest.mark.parametrize(
    "location,category",
    [
        ("San Francisco, CA", LocationCategory.US),
        ("New York, NY", LocationCategory.US),
        ("Seattle, WA", LocationCategory.US),
        ("Austin, TX", LocationCategory.US),
        ("United States", LocationCategory.US),
        ("USA", LocationCategory.US),
        ("US", LocationCategory.US),
        ("Boston, Massachusetts", LocationCategory.US),
        ("Hybrid - San Francisco", LocationCategory.US),
        ("Hybrid NYC", LocationCategory.US),
        ("Remote/San Francisco", LocationCategory.US),
        ("Remote", LocationCategory.REMOTE_US),
        ("Remote US", LocationCategory.REMOTE_US),
        ("US Remote", LocationCategory.REMOTE_US),
        ("Remote - United States", LocationCategory.REMOTE_US),
        ("Remote, USA", LocationCategory.REMOTE_US),
        ("Anywhere in US", LocationCategory.REMOTE_US),
        ("Work from home", LocationCategory.REMOTE_US),
    ],
)
def test_accepted_us_and_remote(location: str, category: LocationCategory) -> None:
    assert classify_location(location) == category
    assert is_us_or_remote(location)


@pytest.mark.parametrize(
    "location",
    [
        "London, UK",
        "Berlin, Germany",
        "Toronto, Canada",
        "Vancouver, BC, Canada",
        "India",
        "Singapore",
        "Dublin, Ireland",
        "Amsterdam, Netherlands",
        "Tokyo, Japan",
        "Sydney, Australia",
        "Remote EMEA",
        "Remote Europe",
        "Remote Canada",
        "Remote India",
        "Paris, France",
        "Remote - UK",
    ],
)
def test_rejected_international(location: str) -> None:
    assert classify_location(location) == LocationCategory.INTERNATIONAL
    assert not is_us_or_remote(location)


@pytest.mark.parametrize(
    "location",
    [
        "EMEA",
        "APAC",
        "Multiple Locations",
        "TBD",
    ],
)
def test_unknown_locations(location: str) -> None:
    assert classify_location(location) == LocationCategory.UNKNOWN
    assert not is_us_or_remote(location)


def test_mixed_us_and_international_rejected() -> None:
    loc = "San Francisco, CA | London, UK"
    assert classify_location(loc) == LocationCategory.INTERNATIONAL
    assert not is_us_or_remote(loc)


def test_mixed_us_and_remote_accepted() -> None:
    loc = "New York, NY or Remote"
    assert classify_location(loc) == LocationCategory.US
    assert is_us_or_remote(loc)


def test_none_location() -> None:
    assert classify_location(None) == LocationCategory.UNKNOWN
    assert not is_us_or_remote(None)
