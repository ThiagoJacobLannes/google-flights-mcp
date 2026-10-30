import pytest

from google_flights_mcp.models import PassengerCounts


def test_defaults_to_one_adult():
    assert PassengerCounts() == PassengerCounts(adults=1, children=0, infants=0)


def test_rejects_zero_adults():
    with pytest.raises(ValueError, match="adult"):
        PassengerCounts(adults=0)


def test_rejects_more_lap_infants_than_adults():
    with pytest.raises(ValueError, match="infant"):
        PassengerCounts(adults=1, infants=2)


def test_rejects_more_than_nine_total_passengers():
    with pytest.raises(ValueError, match="Too many"):
        PassengerCounts(adults=5, children=5)


def test_accepts_a_full_family():
    counts = PassengerCounts(adults=2, children=2, infants=1)
    assert counts.adults + counts.children + counts.infants == 5
