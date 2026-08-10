from scripts.run_alpha_stooq_composite_evidence import _parse_case


def test_parser_symbol_normalization_smoke() -> None:
    parsed = _parse_case("spy,spy.us,instrument:spy,stooq:spy,2026-01-01,2026-01-02")
    assert parsed[0] == "SPY"
    assert parsed[1] == "SPY.US"
