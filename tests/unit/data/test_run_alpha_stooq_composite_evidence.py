from datetime import date

import pytest
from scripts.run_alpha_stooq_composite_evidence import _parse_case


def test_parse_case_normalizes_symbols_and_dates() -> None:
    parsed = _parse_case("spy,spy.us,instrument:spy,stooq:spy,2026-01-01,2026-01-31")
    assert parsed == (
        "SPY",
        "SPY.US",
        "instrument:spy",
        "stooq:spy",
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def test_parse_case_rejects_unbounded_period() -> None:
    with pytest.raises(SystemExit, match="180 calendar days"):
        _parse_case("SPY,SPY.US,instrument:spy,stooq:spy,2025-01-01,2026-01-01")
