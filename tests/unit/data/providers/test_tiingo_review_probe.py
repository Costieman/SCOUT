from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import trade_scout.data.providers.tiingo_review_probe as probe_module
from trade_scout.data.providers.tiingo_review_probe import build_tiingo_review_probe


def _symbol_profile(symbol: str, first_date: str) -> dict[str, object]:
    return {
        "source_symbol": symbol,
        "receipt_id": f"receipt-{symbol}",
        "payload_checksum_sha256": "a" * 64,
        "row_count": 100,
        "first_date": first_date,
        "last_date": "2026-08-07",
        "invalid_date_row_count": 0,
        "duplicate_date_count": 0,
        "non_monotonic_date_count": 0,
        "missing_required_field_row_count": 0,
        "invalid_numeric_row_count": 0,
        "ohlc_invariant_violation_count": 0,
        "negative_volume_count": 0,
        "split_event_count": 2,
        "dividend_event_count": 3,
        "long_calendar_gap_count": 0,
    }


def test_probe_returns_only_acquired_targets_awaiting_review(tmp_path: Path, monkeypatch) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": "tiingo-durable-profile-v0.1",
                "symbols": [
                    _symbol_profile("OLD", "2000-01-03"),
                    _symbol_profile("NEW", "2001-01-02"),
                    _symbol_profile("OTHER", "2002-01-02"),
                ],
            }
        ),
        encoding="utf-8",
    )
    reviewed_id = "reviewed-id"
    candidate = SimpleNamespace(
        coverage_gaps=(),
        provider_series_links=(
            SimpleNamespace(query_symbol="OLD", provider_id="tiingo", instrument_id=reviewed_id),
        ),
    )
    monkeypatch.setattr(
        probe_module,
        "load_reviewed_identity_snapshot_candidate",
        lambda _path: candidate,
    )

    rows = build_tiingo_review_probe(
        profile_path=profile_path,
        candidate_path=tmp_path / "candidate.json",
        target_symbols={"OLD", "NEW", "PENDING"},
        acquired_symbols={"OLD", "NEW", "OTHER"},
    )

    assert len(rows) == 1
    assert rows[0].source_symbol == "NEW"
    assert rows[0].first_date == "2001-01-02"
    assert rows[0].structural_anomaly_count == 0
    assert rows[0].split_event_count == 2
    assert rows[0].dividend_event_count == 3
