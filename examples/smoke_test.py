"""Real, no-mocks smoke test: search LIS -> GRU about a month from now.

Hits Google Flights for real (or SerpApi if SERPAPI_KEY is set) — needs
network access. Run with:

    uv run --project tools/google-flights-mcp python examples/smoke_test.py

or, from an installed venv:

    python examples/smoke_test.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_flights_mcp.models import PassengerCounts
from google_flights_mcp.providers.factory import get_provider


def main() -> int:
    departure = date.today() + timedelta(days=30)
    provider = get_provider()
    print(f"Provider: {provider.name}")
    print(f"Searching LIS -> GRU on {departure.isoformat()} ...")

    try:
        options = provider.search_flights(
            origin="LIS",
            destination="GRU",
            departure_date=departure.isoformat(),
            return_date=None,
            passengers=PassengerCounts(adults=1),
            cabin_class="economy",
            currency="EUR",
            max_stops=None,
        )
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1

    if not options:
        print("FAILED: no results returned", file=sys.stderr)
        return 1

    options.sort(key=lambda o: o.price if o.price is not None else float("inf"))
    print(f"Got {len(options)} result(s). Cheapest 3:")
    for option in options[:3]:
        airlines = ", ".join(option.airlines)
        print(f"  {option.price} {option.currency} — {airlines} — {option.stops} stop(s) — {option.total_duration_minutes} min")
    print(f"Link: {options[0].booking_link}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
