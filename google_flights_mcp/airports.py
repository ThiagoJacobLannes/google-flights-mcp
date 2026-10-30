"""Resolve a free-text city/airport name to IATA code(s).

Backed by the `airportsdata` package's bundled, offline dataset — no
network calls, no API key.
"""

from __future__ import annotations

from dataclasses import dataclass

import airportsdata

_IATA = airportsdata.load("IATA")


@dataclass(frozen=True)
class AirportMatch:
    iata: str
    name: str
    city: str
    country: str


def resolve_airport(query: str, limit: int = 5) -> list[AirportMatch]:
    """Find airports matching a city or airport name.

    Exact 3-letter IATA codes are matched directly. Otherwise this does a
    simple case-insensitive match against city and airport names, ranking
    exact city matches first, then city-prefix, then substring matches.
    """
    q = query.strip()
    if not q:
        return []

    upper = q.upper()
    if len(upper) == 3 and upper.isalpha() and upper in _IATA:
        rec = _IATA[upper]
        return [AirportMatch(iata=upper, name=rec["name"], city=rec["city"], country=rec["country"])]

    q_lower = q.lower()
    scored: list[tuple[int, str, AirportMatch]] = []
    for code, rec in _IATA.items():
        city = rec.get("city") or ""
        name = rec.get("name") or ""
        city_lower = city.lower()
        name_lower = name.lower()

        if city_lower == q_lower:
            score = 0
        elif city_lower.startswith(q_lower):
            score = 1
        elif q_lower in city_lower:
            score = 2
        elif q_lower in name_lower:
            score = 3
        else:
            continue

        scored.append((score, name, AirportMatch(iata=code, name=name, city=city, country=rec.get("country", ""))))

    scored.sort(key=lambda t: (t[0], t[1]))
    return [match for _, _, match in scored[:limit]]
