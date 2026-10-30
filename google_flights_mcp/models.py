"""Shared data types, independent of any specific flight-data provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CabinClass = Literal["economy", "premium", "business", "first"]


@dataclass(frozen=True)
class PassengerCounts:
    """Passenger composition for a search.

    `infants` are treated as lap infants (under 2, no own seat) — the
    common case. Travelers needing a seated infant fare should be counted
    as a child instead.
    """

    adults: int = 1
    children: int = 0
    infants: int = 0

    def __post_init__(self) -> None:
        if self.adults < 1:
            raise ValueError("At least 1 adult passenger is required.")
        if self.infants > self.adults:
            raise ValueError("Need at least one adult per lap infant.")
        total = self.adults + self.children + self.infants
        if total > 9:
            raise ValueError(f"Too many passengers ({total}); Google Flights supports at most 9 per search.")


@dataclass(frozen=True)
class FlightLeg:
    """One physical segment (a single takeoff-to-landing hop) of an itinerary."""

    origin: str
    origin_name: str
    destination: str
    destination_name: str
    departure: str
    """Local departure time, "YYYY-MM-DD HH:MM"."""
    arrival: str
    """Local arrival time, "YYYY-MM-DD HH:MM"."""
    duration_minutes: int | None
    aircraft: str | None = None
    flight_number: str | None = None


@dataclass(frozen=True)
class FlightOption:
    """One priced itinerary returned by a provider.

    For round trips, `legs`/`stops`/`total_duration_minutes` describe the
    OUTBOUND journey only — both fast-flights and SerpApi's Google Flights
    scrape return outbound options annotated with an estimated round-trip
    total price, not a fully itemized return leg. Use `booking_link` to see
    (and pick) the exact return flight on Google Flights.
    """

    price: float | None
    currency: str
    airlines: list[str]
    legs: list[FlightLeg]
    stops: int
    total_duration_minutes: int | None
    booking_link: str | None
    source: str


@dataclass(frozen=True)
class DayPrice:
    """The cheapest fare found for a single departure date."""

    date: str
    price: float | None
    currency: str
    booking_link: str | None = None
