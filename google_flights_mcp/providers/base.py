"""Provider-agnostic interface for flight-data sources.

Swapping the data source (fast-flights vs. SerpApi vs. anything future) means
implementing this interface — nothing in server.py or the tool definitions
needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta

from ..models import CabinClass, DayPrice, FlightOption, PassengerCounts

MAX_CHEAPEST_DATES_WINDOW_DAYS = 21
"""Cap on the cheapest_dates window: it runs one search per day, so a wide
window means a lot of sequential requests against a scraped source."""


class ProviderError(Exception):
    """A provider-level failure: network, parsing, or an unexpected response shape."""


class NoFlightsFoundError(ProviderError):
    """The search reached the provider fine but it had nothing for this route/date."""


class FlightProvider(ABC):
    name: str

    @abstractmethod
    def search_flights(
        self,
        *,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None,
        passengers: PassengerCounts,
        cabin_class: CabinClass,
        currency: str,
        max_stops: int | None,
    ) -> list[FlightOption]:
        """Search flights for one origin/destination/date combination."""
        raise NotImplementedError

    def cheapest_dates(
        self,
        *,
        origin: str,
        destination: str,
        start_date: str,
        end_date: str,
        trip_length: int | None,
        passengers: PassengerCounts,
        cabin_class: CabinClass,
        currency: str,
        max_stops: int | None,
    ) -> list[DayPrice]:
        """Cheapest fare per departure day across a date window.

        Default implementation: brute-force one `search_flights` call per
        day (neither fast-flights nor SerpApi's Google Flights engine expose
        a dedicated price-calendar endpoint). A provider that gains access to
        a real calendar API can override this for something cheaper/faster.
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise ValueError("start_date must not be after end_date.")

        span_days = (end - start).days + 1
        if span_days > MAX_CHEAPEST_DATES_WINDOW_DAYS:
            raise ValueError(
                f"Date range spans {span_days} days; max is {MAX_CHEAPEST_DATES_WINDOW_DAYS} "
                "to keep the number of searches reasonable."
            )

        results: list[DayPrice] = []
        for offset in range(span_days):
            day = start + timedelta(days=offset)
            return_date = (day + timedelta(days=trip_length)).isoformat() if trip_length else None
            try:
                options = self.search_flights(
                    origin=origin,
                    destination=destination,
                    departure_date=day.isoformat(),
                    return_date=return_date,
                    passengers=passengers,
                    cabin_class=cabin_class,
                    currency=currency,
                    max_stops=max_stops,
                )
            except NoFlightsFoundError:
                continue

            if not options:
                continue

            cheapest = min(options, key=lambda o: o.price if o.price is not None else float("inf"))
            results.append(
                DayPrice(date=day.isoformat(), price=cheapest.price, currency=currency, booking_link=cheapest.booking_link)
            )

        return results
