"""FastMCP server exposing Google Flights search as MCP tools."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .airports import resolve_airport
from .models import CabinClass, FlightOption, PassengerCounts
from .providers.base import NoFlightsFoundError, ProviderError
from .providers.factory import get_provider

DEFAULT_ORIGIN = os.environ.get("GOOGLE_FLIGHTS_DEFAULT_ORIGIN", "LIS")
DEFAULT_CURRENCY = os.environ.get("GOOGLE_FLIGHTS_DEFAULT_CURRENCY", "EUR")
_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
_PORT = int(os.environ.get("MCP_PORT", "8000"))

mcp = FastMCP(
    "google-flights",
    instructions=(
        "Search Google Flights for prices, schedules, and the cheapest travel dates. "
        f"Origin defaults to {DEFAULT_ORIGIN} and currency defaults to {DEFAULT_CURRENCY} "
        "when not specified. If you're unsure of an airport's IATA code, call "
        "airport_search first."
    ),
    host=_HOST,
    port=_PORT,
)


def _validate_iata(code: str, field_name: str) -> str:
    code = (code or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ToolError(
            f"'{code}' is not a valid 3-letter IATA airport code for {field_name}. "
            "Use the airport_search tool to look it up."
        )
    return code


def _validate_date(value: str, field_name: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as e:
        raise ToolError(f"{field_name} must be in YYYY-MM-DD format, got '{value}'.") from e
    return value


def _passenger_counts(adults: int, children: int, infants: int) -> PassengerCounts:
    try:
        return PassengerCounts(adults=adults, children=children, infants=infants)
    except ValueError as e:
        raise ToolError(str(e)) from e


def _option_to_dict(option: FlightOption) -> dict:
    return {
        "price": option.price,
        "currency": option.currency,
        "airlines": option.airlines,
        "stops": option.stops,
        "total_duration_minutes": option.total_duration_minutes,
        "legs": [asdict(leg) for leg in option.legs],
        "booking_link": option.booking_link,
        "source": option.source,
    }


@mcp.tool()
def search_flights(
    destination: str,
    departure_date: str,
    origin: str = DEFAULT_ORIGIN,
    return_date: str | None = None,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    cabin_class: CabinClass = "economy",
    currency: str = DEFAULT_CURRENCY,
    max_stops: int | None = None,
    sort_by: Literal["price", "duration"] = "price",
) -> dict:
    """Search flight prices and options on Google Flights.

    Args:
        destination: Destination airport IATA code (e.g. "GRU"). If you only
            have a city name, call airport_search first.
        departure_date: Outbound date, YYYY-MM-DD.
        origin: Origin airport IATA code. Defaults to Lisbon (LIS) if omitted.
        return_date: Return date YYYY-MM-DD to search a round trip; omit for
            one-way. For round trips, each result's price is Google's
            estimated round-trip total for that outbound flight paired with
            its cheapest matching return — stops/duration/legs describe the
            outbound only. Open booking_link to pick the exact return flight.
        adults: Number of adult passengers (default 1).
        children: Number of child passengers (default 0).
        infants: Number of lap infants, under 2 with no own seat (default 0).
        cabin_class: "economy" | "premium" | "business" | "first".
        currency: ISO currency code. Defaults to EUR.
        max_stops: Maximum stops to allow (0 = nonstop only, 1 = up to one
            stop, etc.). Omit to allow any number of stops.
        sort_by: "price" (default, ascending) or "duration" (ascending).
    """
    origin = _validate_iata(origin, "origin")
    destination = _validate_iata(destination, "destination")
    departure_date = _validate_date(departure_date, "departure_date")
    if return_date:
        return_date = _validate_date(return_date, "return_date")

    passengers = _passenger_counts(adults, children, infants)
    provider = get_provider()

    try:
        options = provider.search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passengers=passengers,
            cabin_class=cabin_class,
            currency=currency.upper(),
            max_stops=max_stops,
        )
    except (NoFlightsFoundError, ProviderError, ValueError) as e:
        raise ToolError(str(e)) from e

    if not options:
        raise ToolError(f"No flights found for {origin}→{destination} on {departure_date}.")

    sort_key = (
        (lambda o: o.total_duration_minutes if o.total_duration_minutes is not None else float("inf"))
        if sort_by == "duration"
        else (lambda o: o.price if o.price is not None else float("inf"))
    )
    options = sorted(options, key=sort_key)

    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "currency": currency.upper(),
        "provider": provider.name,
        "results": [_option_to_dict(o) for o in options],
    }


@mcp.tool()
def cheapest_dates(
    destination: str,
    start_date: str,
    end_date: str,
    origin: str = DEFAULT_ORIGIN,
    trip_length: int | None = None,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    cabin_class: CabinClass = "economy",
    currency: str = DEFAULT_CURRENCY,
    max_stops: int | None = None,
) -> dict:
    """Find the cheapest day(s) to fly within a date window (price-calendar style).

    Runs one search per candidate departure day in the window (capped at 21
    days — neither of this server's data sources expose a real bulk
    price-calendar endpoint) and returns each day's cheapest fare, sorted by
    price ascending.

    Args:
        destination: Destination airport IATA code.
        start_date: First candidate departure date, YYYY-MM-DD.
        end_date: Last candidate departure date, YYYY-MM-DD (inclusive; max
            21 days after start_date).
        origin: Origin airport IATA code. Defaults to Lisbon (LIS).
        trip_length: Nights for a round trip, applied to every departure day
            in the window. Omit to price one-way fares.
        adults, children, infants: Passenger counts (see search_flights).
        cabin_class: "economy" | "premium" | "business" | "first".
        currency: ISO currency code. Defaults to EUR.
        max_stops: Maximum stops to allow. Omit to allow any.
    """
    origin = _validate_iata(origin, "origin")
    destination = _validate_iata(destination, "destination")
    start_date = _validate_date(start_date, "start_date")
    end_date = _validate_date(end_date, "end_date")
    if trip_length is not None and trip_length < 1:
        raise ToolError("trip_length must be at least 1 night.")

    passengers = _passenger_counts(adults, children, infants)
    provider = get_provider()

    try:
        days = provider.cheapest_dates(
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            trip_length=trip_length,
            passengers=passengers,
            cabin_class=cabin_class,
            currency=currency.upper(),
            max_stops=max_stops,
        )
    except (NoFlightsFoundError, ProviderError, ValueError) as e:
        raise ToolError(str(e)) from e

    if not days:
        raise ToolError(f"No flights found for {origin}→{destination} between {start_date} and {end_date}.")

    days = sorted(days, key=lambda d: d.price if d.price is not None else float("inf"))

    return {
        "origin": origin,
        "destination": destination,
        "currency": currency.upper(),
        "trip_length_nights": trip_length,
        "provider": provider.name,
        "days": [asdict(d) for d in days],
    }


@mcp.tool()
def airport_search(query: str, limit: int = 5) -> dict:
    """Resolve a city or airport name to IATA code(s), e.g. "Lisbon" -> LIS.

    Args:
        query: A city name, airport name, or 3-letter IATA code.
        limit: Maximum number of matches to return (default 5).
    """
    matches = resolve_airport(query, limit=limit)
    if not matches:
        raise ToolError(f"No airport found matching '{query}'.")
    return {"query": query, "matches": [asdict(m) for m in matches]}


def main() -> None:
    use_http = "--http" in sys.argv or os.environ.get("MCP_TRANSPORT") == "streamable-http"
    mcp.run(transport="streamable-http" if use_http else "stdio")


if __name__ == "__main__":
    main()
