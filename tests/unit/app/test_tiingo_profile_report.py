import json
from pathlib import Path

import pytest

from trade_scout.app.tiingo_profile_report import (
    TiingoProfileReportError,
    load_tiingo_profile_view,
    render_tiingo_profile_html,
)


def _profile() -> dict[str, object]:
    return {
        "schema_version": "tiingo-durable-profile-v0.1",
        "generated_at": "2026-08-10T07:00:00+00:00",
        "storage_namespace": "private-test-v1",
        "receipt_count": 2,
        "symbol_count": 2,
        "total_row_count": 5,
        "invalid_date_row_count": 0,
        "duplicate_date_count": 0,
        "non_monotonic_date_count": 0,
        "missing_required_field_row_count": 0,
        "invalid_numeric_row_count": 0,
        "ohlc_invariant_violation_count": 0,
        "negative_volume_count": 0,
        "split_event_count": 1,
        "dividend_event_count": 2,
        "long_calendar_gap_count": 0,
        "symbols": [
            {
                "source_symbol": "AAPL",
                "receipt_id": "receipt-aapl",
                "payload_checksum_sha256": "a" * 64,
                "row_count": 3,
                "first_date": "2020-08-28",
                "last_date": "2020-09-01",
                "invalid_date_row_count": 0,
                "duplicate_date_count": 0,
                "non_monotonic_date_count": 0,
                "missing_required_field_row_count": 0,
                "invalid_numeric_row_count": 0,
                "ohlc_invariant_violation_count": 0,
                "negative_volume_count": 0,
                "split_event_count": 1,
                "dividend_event_count": 1,
                "long_calendar_gap_count": 0,
            },
            {
                "source_symbol": "ABNB",
                "receipt_id": "receipt-abnb",
                "payload_checksum_sha256": "b" * 64,
                "row_count": 2,
                "first_date": "2020-12-10",
                "last_date": "2020-12-11",
                "invalid_date_row_count": 0,
                "duplicate_date_count": 0,
                "non_monotonic_date_count": 0,
                "missing_required_field_row_count": 0,
                "invalid_numeric_row_count": 0,
                "ohlc_invariant_violation_count": 0,
                "negative_volume_count": 0,
                "split_event_count": 0,
                "dividend_event_count": 1,
                "long_calendar_gap_count": 0,
            },
        ],
    }


def test_load_and_render_profile_without_raw_prices(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(_profile()), encoding="utf-8")

    view = load_tiingo_profile_view(path)
    assert view.symbol_count == 2
    assert view.total_row_count == 5
    assert view.symbols_with_structural_anomalies == 0

    html = render_tiingo_profile_html(view)
    assert "AAPL" in html
    assert "ABNB" in html
    assert "Profiled rows" in html
    assert "open" not in html.lower()
    assert "adjclose" not in html.lower()


def test_rejects_inconsistent_total_row_count(tmp_path: Path) -> None:
    payload = _profile()
    payload["total_row_count"] = 99
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TiingoProfileReportError, match="total_row_count"):
        load_tiingo_profile_view(path)
