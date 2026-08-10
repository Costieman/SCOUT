import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.data.durable_raw_receipt import (
    create_durable_raw_receipt,
    persist_durable_raw_receipt,
)
from trade_scout.data.providers.tiingo_profile import (
    TiingoProfileError,
    persist_tiingo_durable_profile,
    profile_durable_tiingo,
)
from trade_scout.data.raw_store import RawBatchStore


def _rows() -> list[dict[str, object]]:
    return [
        {
            "date": "2020-08-28T00:00:00+00:00",
            "open": 500.0,
            "high": 505.0,
            "low": 495.0,
            "close": 499.0,
            "volume": 1000,
            "adjOpen": 125.0,
            "adjHigh": 126.25,
            "adjLow": 123.75,
            "adjClose": 124.75,
            "divCash": 0.0,
            "splitFactor": 1.0,
        },
        {
            "date": "2020-08-31T00:00:00+00:00",
            "open": 127.0,
            "high": 131.0,
            "low": 126.0,
            "close": 129.0,
            "volume": 2000,
            "adjOpen": 127.0,
            "adjHigh": 131.0,
            "adjLow": 126.0,
            "adjClose": 129.0,
            "divCash": 0.0,
            "splitFactor": 4.0,
        },
        {
            "date": "2020-09-01T00:00:00+00:00",
            "open": 132.0,
            "high": 134.0,
            "low": 130.0,
            "close": 131.0,
            "volume": 1500,
            "adjOpen": 132.0,
            "adjHigh": 134.0,
            "adjLow": 130.0,
            "adjClose": 131.0,
            "divCash": 0.25,
            "splitFactor": 1.0,
        },
    ]


def _persist_receipt(
    tmp_path: Path,
    *,
    subject: str = "AAPL",
    batch_id: str = "batch-aapl",
    retrieval_time: datetime | None = None,
) -> tuple[Path, Path]:
    raw_root = tmp_path / "raw"
    receipt_root = tmp_path / "receipts"
    observed_at = retrieval_time or datetime(2026, 8, 10, 6, 0, tzinfo=UTC)
    record = RawBatchStore(raw_root).persist(
        json.dumps(_rows()).encode(),
        batch_id=batch_id,
        provider_id="tiingo",
        endpoint=f"/tiingo/daily/{subject}/prices",
        retrieval_time=observed_at,
        request_parameters={
            "startDate": "1996-01-02",
            "endDate": "2026-08-07",
            "resampleFreq": "daily",
        },
        media_type="application/json",
    )
    receipt = create_durable_raw_receipt(
        record,
        durable_root=raw_root,
        storage_namespace="private-test-v1",
        subject_key=subject,
    )
    persist_durable_raw_receipt(
        receipt_root / subject / f"{receipt.receipt_id}.json",
        receipt,
    )
    return raw_root, receipt_root


def test_profile_emits_only_derived_diagnostics(tmp_path: Path) -> None:
    raw_root, receipt_root = _persist_receipt(tmp_path)
    profile = profile_durable_tiingo(
        receipt_root=receipt_root,
        raw_root=raw_root,
        storage_namespace="private-test-v1",
        generated_at=datetime(2026, 8, 10, 7, 0, tzinfo=UTC),
    )

    assert profile.symbol_count == 1
    assert profile.total_row_count == 3
    assert profile.split_event_count == 1
    assert profile.dividend_event_count == 1
    assert profile.duplicate_date_count == 0
    assert profile.ohlc_invariant_violation_count == 0
    symbol = profile.symbols[0]
    assert symbol.source_symbol == "AAPL"
    assert symbol.first_date == "2020-08-28"
    assert symbol.last_date == "2020-09-01"

    output = tmp_path / "profile.json"
    persist_tiingo_durable_profile(output, profile)
    payload = json.loads(output.read_text(encoding="utf-8"))
    symbol_payload = payload["symbols"][0]
    assert "open" not in symbol_payload
    assert "close" not in symbol_payload
    assert "volume" not in symbol_payload
    assert "adjClose" not in symbol_payload


def test_profile_fails_closed_on_multiple_receipts_for_one_subject(tmp_path: Path) -> None:
    raw_root, receipt_root = _persist_receipt(tmp_path)
    _persist_receipt(
        tmp_path,
        batch_id="batch-aapl-2",
        retrieval_time=datetime(2026, 8, 10, 6, 1, tzinfo=UTC),
    )

    with pytest.raises(TiingoProfileError, match="multiple durable receipts"):
        profile_durable_tiingo(
            receipt_root=receipt_root,
            raw_root=raw_root,
            storage_namespace="private-test-v1",
        )
