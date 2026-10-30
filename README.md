# google-flights-mcp

MCP server for searching Google Flights prices and schedules from Claude.

Two interchangeable data sources behind one interface (`google_flights_mcp/providers/base.py`):

- **`fast-flights`** (default) — scrapes Google Flights' internal protobuf search API directly. No API key, works out of the box.
- **SerpApi** — used automatically when a `SERPAPI_KEY` environment variable is set. Adds flight numbers, layover detail, and carbon emissions.

## Tools

- **`search_flights`** — `origin` (default `LIS`), `destination`, `departure_date`, optional `return_date`, passenger counts, `cabin_class`, `currency` (default `EUR`), `max_stops`, `sort_by`. Returns a price-ranked list: price, airline(s), departure/arrival times, duration, stops, and a Google Flights link.
- **`cheapest_dates`** — cheapest day(s) to fly in a date window (max 21 days), price-calendar style. Runs one search per day — see "Known limitations" below.
- **`airport_search`** — resolve a city or airport name ("Lisbon") to an IATA code (`LIS`), backed by the offline `airportsdata` package.

## Known limitations

- **Round trips**: for `return_date` searches, both providers return *outbound* flight options annotated with an estimated round-trip total price (paired with the cheapest matching return) — not a separately priced return leg. `stops`/`duration`/`legs` describe the outbound flight only. Open the result's `booking_link` on Google Flights to pick the exact return.
- **`cheapest_dates`**: neither `fast-flights` nor SerpApi's Google Flights engine expose a real bulk price-calendar endpoint, so this runs one `search_flights` call per candidate day. Capped at a 21-day window to keep that bounded.
- **EU/UK cookie-consent wall**: Google shows a cookie-consent interstitial to requests from those regions before returning real results. The `fast-flights` provider detects this and auto-submits "Reject all" (the privacy-preserving option) before retrying — see `providers/fast_flights_provider.py` if this ever needs updating for a change on Google's side.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ThiagoJacobLannes/google-flights-mcp
cd google-flights-mcp
uv sync --extra dev
```

On Windows, if you keep code in a cloud-synced folder (Google Drive, OneDrive), create the venv **outside** it — sync clients drop `desktop.ini` marker files into folders, which can crash packages on startup:

```bash
uv venv C:\dev\google-flights-mcp-venv
uv pip install --python C:\dev\google-flights-mcp-venv -e ".[dev]"
```

The command paths below assume that venv location; adjust to wherever yours lives.

## Add to Claude Desktop

Merge `claude_desktop_config.snippet.json` into your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "google-flights": {
      "command": "C:\\dev\\google-flights-mcp-venv\\Scripts\\python.exe",
      "args": ["-m", "google_flights_mcp.server"]
    }
  }
}
```

Restart Claude Desktop after editing. To use SerpApi instead of the default scraper, add an `env` block:

```json
{
  "mcpServers": {
    "google-flights": {
      "command": "C:\\dev\\google-flights-mcp-venv\\Scripts\\python.exe",
      "args": ["-m", "google_flights_mcp.server"],
      "env": { "SERPAPI_KEY": "your-serpapi-key" }
    }
  }
}
```

Get a key at [serpapi.com](https://serpapi.com/) (free tier available).

Other env vars: `GOOGLE_FLIGHTS_DEFAULT_ORIGIN` (default `LIS`), `GOOGLE_FLIGHTS_DEFAULT_CURRENCY` (default `EUR`).

## Running over HTTP (for a remote connector)

```bash
C:\dev\google-flights-mcp-venv\Scripts\python.exe -m google_flights_mcp.server --http
```

Or set `MCP_TRANSPORT=streamable-http`. Configure the bind address with `MCP_HOST` (default `127.0.0.1`) and `MCP_PORT` (default `8000`); the server listens at `http://<host>:<port>/mcp`. Put this behind whatever reverse proxy / auth you use for your other remote connectors before exposing it beyond localhost.

## Smoke test

Real network call (no mocks) — searches LIS → GRU about a month out:

```bash
C:\dev\google-flights-mcp-venv\Scripts\python.exe tools\google-flights-mcp\examples\smoke_test.py
```

## Tests

```bash
C:\dev\google-flights-mcp-venv\Scripts\python.exe -m pytest tools\google-flights-mcp\tests
```

These are unit tests against the provider abstraction (factory selection, passenger validation, the shared `cheapest_dates` day-loop, airport resolution) — no network access required.
