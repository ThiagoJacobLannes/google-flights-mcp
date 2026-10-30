from google_flights_mcp.airports import resolve_airport


def test_exact_iata_code():
    matches = resolve_airport("GRU")
    assert len(matches) == 1
    assert matches[0].iata == "GRU"


def test_city_name_resolves_to_expected_code():
    matches = resolve_airport("Lisbon")
    assert any(m.iata == "LIS" for m in matches)


def test_lowercase_and_partial_city_name():
    matches = resolve_airport("lisb")
    assert any(m.iata == "LIS" for m in matches)


def test_no_match_returns_empty_list():
    assert resolve_airport("Not A Real City Zzzqx") == []


def test_blank_query_returns_empty_list():
    assert resolve_airport("   ") == []


def test_limit_is_respected():
    matches = resolve_airport("San", limit=2)
    assert len(matches) <= 2
