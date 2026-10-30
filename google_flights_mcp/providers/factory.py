"""Picks the active provider: SerpApi if SERPAPI_KEY is set, else fast-flights."""

from __future__ import annotations

import os

from .base import FlightProvider
from .fast_flights_provider import FastFlightsProvider


def get_provider() -> FlightProvider:
    api_key = os.environ.get("SERPAPI_KEY")
    if api_key:
        from .serpapi_provider import SerpApiProvider

        return SerpApiProvider(api_key=api_key)
    return FastFlightsProvider()
