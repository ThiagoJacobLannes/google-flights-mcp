"""Default provider: scrapes Google Flights directly via `fast-flights`.

No API key needed. `fast-flights` decodes Google's internal protobuf search
API — no browser, no HTML form-filling for the search itself.

One thing `fast-flights` 3.0.2 does NOT handle on its own: Google shows an
EU/UK cookie-consent interstitial (a redirect to consent.google.com) before
the real results for requests coming from those regions, and the library's
built-in fetcher chokes on it (empty results). This module fetches the page
itself, and when it lands on the consent page, auto-submits the "Reject all"
option (the privacy-preserving choice — accepting is not needed to see
flight results) and retries once.
"""

from __future__ import annotations

import html as htmlmod
from datetime import datetime

from fast_flights import FlightQuery, create_query
from fast_flights import Passengers as FFPassengers
from fast_flights.exceptions import FlightsNotFound
from fast_flights.model import Flights as FFFlights
from fast_flights.model import SimpleDatetime
from fast_flights.parser import parse as parse_flights_html
from primp import Client
from selectolax.lexbor import LexborHTMLParser

from ..models import CabinClass, FlightLeg, FlightOption, PassengerCounts
from .base import FlightProvider, NoFlightsFoundError, ProviderError

_SEARCH_URL = "https://www.google.com/travel/flights"
_CONSENT_SAVE_URL = "https://consent.google.com/save"

_SEAT_MAP: dict[str, str] = {
    "economy": "economy",
    "premium": "premium-economy",
    "business": "business",
    "first": "first",
}


class FastFlightsProvider(FlightProvider):
    name = "fast-flights"

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
        flight_legs = [FlightQuery(date=departure_date, from_airport=origin, to_airport=destination)]
        trip = "one-way"
        if return_date:
            flight_legs.append(FlightQuery(date=return_date, from_airport=destination, to_airport=origin))
            trip = "round-trip"

        try:
            query = create_query(
                flights=flight_legs,
                seat=_SEAT_MAP[cabin_class],
                trip=trip,
                passengers=FFPassengers(
                    adults=passengers.adults,
                    children=passengers.children,
                    infants_on_lap=passengers.infants,
                ),
                currency=currency,
                max_stops=max_stops,
            )
        except AssertionError as e:
            raise ProviderError(str(e)) from e

        client = Client(impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True)
        try:
            html_text = _fetch_with_consent_bypass(client, query)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Could not reach Google Flights: {e}") from e

        try:
            parsed = parse_flights_html(html_text)
        except FlightsNotFound as e:
            raise NoFlightsFoundError(f"No flights found for {origin}→{destination} on {departure_date}.") from e
        except Exception as e:
            raise ProviderError(f"Could not parse the Google Flights response: {e}") from e

        link = query.url()
        options = [_to_option(flight, currency, link) for flight in parsed]
        if max_stops is not None:
            # Defensive: Google's own filter has already been asked to do this via
            # FlightQuery.max_stops, but don't rely solely on that holding.
            options = [o for o in options if o.stops <= max_stops]
        return options


def _fetch_with_consent_bypass(client: Client, query) -> str:
    res = client.get(_SEARCH_URL, params=query.params())
    if "consent.google.com" not in str(res.url):
        return res.content.decode("utf-8")

    parser = LexborHTMLParser(res.content.decode("utf-8"))
    reject_form: dict[str, str] | None = None
    for form in parser.css("form"):
        data = {
            inp.attributes.get("name"): inp.attributes.get("value")
            for inp in form.css("input[type=hidden]")
            if inp.attributes.get("name")
        }
        # Google renders four consent forms on this page; the one that sets
        # only `set_eom` (no set_sc/set_aps) is "Reject all".
        if data.get("set_eom") == "true" and "set_sc" not in data:
            reject_form = data
            break

    if reject_form is None or "continue" not in reject_form:
        raise ProviderError("Google showed a cookie-consent page this server doesn't know how to bypass.")

    client.post(_CONSENT_SAVE_URL, data=reject_form)
    continue_url = htmlmod.unescape(reject_form["continue"])
    final = client.get(continue_url)
    return final.content.decode("utf-8")


def _hour_minute(time_tuple: tuple[int | None, ...]) -> tuple[int, int]:
    # Google's payload sends `null` (not 0) for a midnight hour, e.g. [None, 40]
    # meaning 00:40 — treat missing/None components as 0.
    hour = time_tuple[0] if time_tuple and time_tuple[0] is not None else 0
    minute = time_tuple[1] if len(time_tuple) > 1 and time_tuple[1] is not None else 0
    return hour, minute


def _format_datetime(date_tuple: tuple[int, ...], time_tuple: tuple[int | None, ...]) -> str:
    year, month, day = date_tuple[0], date_tuple[1], date_tuple[2]
    hour, minute = _hour_minute(time_tuple)
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _minutes_between(dep: SimpleDatetime, arr: SimpleDatetime) -> int | None:
    try:
        dep_hour, dep_minute = _hour_minute(dep.time)
        arr_hour, arr_minute = _hour_minute(arr.time)
        dep_dt = datetime(dep.date[0], dep.date[1], dep.date[2], dep_hour, dep_minute)
        arr_dt = datetime(arr.date[0], arr.date[1], arr.date[2], arr_hour, arr_minute)
        return int((arr_dt - dep_dt).total_seconds() // 60)
    except (IndexError, ValueError):
        return None


def _to_option(flight: FFFlights, currency: str, booking_link: str) -> FlightOption:
    legs = [
        FlightLeg(
            origin=leg.from_airport.code,
            origin_name=leg.from_airport.name,
            destination=leg.to_airport.code,
            destination_name=leg.to_airport.name,
            departure=_format_datetime(leg.departure.date, leg.departure.time),
            arrival=_format_datetime(leg.arrival.date, leg.arrival.time),
            duration_minutes=leg.duration,
            aircraft=leg.plane_type,
        )
        for leg in flight.flights
    ]

    total_duration = None
    if legs:
        total_duration = _minutes_between(flight.flights[0].departure, flight.flights[-1].arrival)
        if total_duration is None:
            total_duration = sum(leg.duration for leg in flight.flights if leg.duration) or None

    return FlightOption(
        price=float(flight.price) if flight.price is not None else None,
        currency=currency,
        airlines=list(flight.airlines),
        legs=legs,
        stops=max(len(legs) - 1, 0),
        total_duration_minutes=total_duration,
        booking_link=booking_link,
        source="fast-flights",
    )
