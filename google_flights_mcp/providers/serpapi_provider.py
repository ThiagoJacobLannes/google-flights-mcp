"""Optional richer provider: SerpApi's Google Flights engine.

Used instead of `fast-flights` when a SERPAPI_KEY environment variable is
set. Trades "no API key needed" for real flight numbers, layover details,
carbon emissions, and (via SerpApi) booking links — see
https://serpapi.com/google-flights-api for the API this wraps.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ..models import CabinClass, FlightLeg, FlightOption, PassengerCounts
from .base import FlightProvider, NoFlightsFoundError, ProviderError

_SERPAPI_URL = "https://serpapi.com/search.json"

_TRAVEL_CLASS_MAP: dict[str, int] = {
    "economy": 1,
    "premium": 2,
    "business": 3,
    "first": 4,
}


def _stops_param(max_stops: int | None) -> int | None:
    """Map "max stops allowed" onto SerpApi's coarser `stops` filter.

    SerpApi only offers nonstop / 1-or-fewer / 2-or-fewer, so max_stops > 2
    is treated the same as "any" (2-or-fewer is the closest available filter).
    """
    if max_stops is None:
        return None
    if max_stops <= 0:
        return 1
    if max_stops == 1:
        return 2
    return 3


class SerpApiProvider(FlightProvider):
    name = "serpapi"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

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
        params: dict[str, str | int] = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": departure_date,
            "type": 1 if return_date else 2,
            "currency": currency,
            "travel_class": _TRAVEL_CLASS_MAP[cabin_class],
            "adults": passengers.adults,
            "children": passengers.children,
            "infants_on_lap": passengers.infants,
            "hl": "en",
            "api_key": self._api_key,
        }
        if return_date:
            params["return_date"] = return_date
        stops = _stops_param(max_stops)
        if stops is not None:
            params["stops"] = stops

        try:
            response = httpx.get(_SERPAPI_URL, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"SerpApi request failed ({e.response.status_code}): {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach SerpApi: {e}") from e
        except ValueError as e:
            raise ProviderError(f"SerpApi returned a response that wasn't valid JSON: {e}") from e

        if error := payload.get("error"):
            raise NoFlightsFoundError(str(error))

        itineraries = [*payload.get("best_flights", []), *payload.get("other_flights", [])]
        if not itineraries:
            raise NoFlightsFoundError(f"No flights found for {origin}→{destination} on {departure_date}.")

        link = (
            payload.get("search_metadata", {}).get("google_flights_url")
            or _fallback_link(origin, destination, departure_date, return_date)
        )
        return [_to_option(itinerary, currency, link) for itinerary in itineraries]


def _fallback_link(origin: str, destination: str, departure_date: str, return_date: str | None) -> str:
    text = f"Flights from {origin} to {destination} on {departure_date}"
    if return_date:
        text += f" returning {return_date}"
    return f"https://www.google.com/travel/flights?q={quote(text)}"


def _to_option(itinerary: dict, currency: str, booking_link: str) -> FlightOption:
    segments = itinerary.get("flights", [])
    legs = [
        FlightLeg(
            origin=seg.get("departure_airport", {}).get("id", ""),
            origin_name=seg.get("departure_airport", {}).get("name", ""),
            destination=seg.get("arrival_airport", {}).get("id", ""),
            destination_name=seg.get("arrival_airport", {}).get("name", ""),
            departure=seg.get("departure_airport", {}).get("time", ""),
            arrival=seg.get("arrival_airport", {}).get("time", ""),
            duration_minutes=seg.get("duration"),
            aircraft=seg.get("airplane"),
            flight_number=seg.get("flight_number"),
        )
        for seg in segments
    ]
    airlines = sorted({seg.get("airline") for seg in segments if seg.get("airline")})
    price = itinerary.get("price")

    return FlightOption(
        price=float(price) if price is not None else None,
        currency=currency,
        airlines=airlines,
        legs=legs,
        stops=max(len(legs) - 1, 0),
        total_duration_minutes=itinerary.get("total_duration"),
        booking_link=booking_link,
        source="serpapi",
    )
