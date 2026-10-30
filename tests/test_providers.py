import pytest

from google_flights_mcp.models import FlightOption, PassengerCounts
from google_flights_mcp.providers.base import FlightProvider, NoFlightsFoundError
from google_flights_mcp.providers.factory import get_provider
from google_flights_mcp.providers.fast_flights_provider import FastFlightsProvider
from google_flights_mcp.providers.serpapi_provider import SerpApiProvider, _stops_param

_PASSENGERS = PassengerCounts(adults=1)


class _StubProvider(FlightProvider):
    """A fake provider whose search_flights is driven entirely by a dict of
    canned per-date prices, so the *shared* cheapest_dates loop logic (in
    FlightProvider.cheapest_dates) can be tested without any network access.
    """

    name = "stub"

    def __init__(self, prices_by_date: dict[str, float | None]):
        self._prices_by_date = prices_by_date

    def search_flights(self, *, departure_date, return_date=None, **kwargs) -> list[FlightOption]:
        price = self._prices_by_date.get(departure_date)
        if price is None:
            raise NoFlightsFoundError(f"no flights on {departure_date}")
        return [
            FlightOption(
                price=price,
                currency="EUR",
                airlines=["Stub Air"],
                legs=[],
                stops=0,
                total_duration_minutes=100,
                booking_link="https://example.invalid/search",
                source=self.name,
            )
        ]


def test_factory_defaults_to_fast_flights(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    assert isinstance(get_provider(), FastFlightsProvider)


def test_factory_uses_serpapi_when_key_present(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "test-key-123")
    provider = get_provider()
    assert isinstance(provider, SerpApiProvider)


def test_cheapest_dates_picks_the_minimum_per_day():
    provider = _StubProvider({"2026-08-20": 500, "2026-08-21": 300, "2026-08-22": 900})
    days = provider.cheapest_dates(
        origin="LIS", destination="GRU", start_date="2026-08-20", end_date="2026-08-22",
        trip_length=None, passengers=_PASSENGERS, cabin_class="economy", currency="EUR", max_stops=None,
    )
    assert [d.price for d in days] == [500, 300, 900]
    assert [d.date for d in days] == ["2026-08-20", "2026-08-21", "2026-08-22"]


def test_cheapest_dates_skips_days_with_no_flights():
    provider = _StubProvider({"2026-08-20": 500, "2026-08-22": 900})
    days = provider.cheapest_dates(
        origin="LIS", destination="GRU", start_date="2026-08-20", end_date="2026-08-22",
        trip_length=None, passengers=_PASSENGERS, cabin_class="economy", currency="EUR", max_stops=None,
    )
    assert [d.date for d in days] == ["2026-08-20", "2026-08-22"]


def test_cheapest_dates_rejects_start_after_end():
    provider = _StubProvider({})
    with pytest.raises(ValueError, match="start_date"):
        provider.cheapest_dates(
            origin="LIS", destination="GRU", start_date="2026-08-25", end_date="2026-08-20",
            trip_length=None, passengers=_PASSENGERS, cabin_class="economy", currency="EUR", max_stops=None,
        )


def test_cheapest_dates_rejects_windows_wider_than_the_cap():
    provider = _StubProvider({})
    with pytest.raises(ValueError, match="max is"):
        provider.cheapest_dates(
            origin="LIS", destination="GRU", start_date="2026-08-01", end_date="2026-09-01",
            trip_length=None, passengers=_PASSENGERS, cabin_class="economy", currency="EUR", max_stops=None,
        )


@pytest.mark.parametrize(
    ("max_stops", "expected"),
    [(None, None), (0, 1), (1, 2), (2, 3), (5, 3)],
)
def test_serpapi_stops_param_mapping(max_stops, expected):
    assert _stops_param(max_stops) == expected
