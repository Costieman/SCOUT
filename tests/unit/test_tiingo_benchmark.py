"""Tests for standalone Tiingo benchmark canonical promotion."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.data.providers.tiingo_benchmark import (
    BENCHMARK_ADJUSTMENT_POLICY_VERSION,
    TiingoBenchmarkDefinition,
    TiingoBenchmarkPromotionError,
    promote_tiingo_benchmark_rows,
)

DATASET = DatasetVersion("benchmark-canonical-v1")
INSTRUMENT = InstrumentId("benchmark-test-id")
START = date(2026, 8, 3)
END = date(2026, 8, 7)


def _definition() -> TiingoBenchmarkDefinition:
    return TiingoBenchmarkDefinition(
        query_symbol="TESTETF",
        provider_instrument_id="tiingo-test-etf",
        instrument_id=INSTRUMENT,
        name="Test Broad Market ETF",
        exchange="XNYS",
        currency="USD",
        first_trade_date=START,
        dataset_start_date=START,
        dataset_end_date=END,
        dataset_version=DATASET,
    )


def _row(day: date, value: float) -> dict[str, object]:
    return {
        "date": day.isoformat(),
        "open": value,
        "high": value + 1.0,
        "low": value - 1.0,
        "close": value + 0.5,
        "volume": 1_000_000,
        "splitFactor": 1.0,
        "divCash": 0.0,
        "adjOpen": value,
        "adjHigh": value + 1.0,
        "adjLow": value - 1.0,
        "adjClose": value + 0.5,
    }


def _rows() -> list[dict[str, object]]:
    return [_row(START + timedelta(days=index), 100.0 + index) for index in range(5)]


def test_benchmark_promotes_as_separate_all_pass_immutable_dataset(tmp_path: Path) -> None:
    result = promote_tiingo_benchmark_rows(
        _rows(),
        definition=_definition(),
        canonical_root=tmp_path,
        source_batch_ids=("raw-benchmark-batch",),
        promoted_at=datetime(2026, 8, 13, tzinfo=UTC),
    )

    assert result.session_audit.complete
    assert result.manifest.record_count == 5
    assert result.manifest.adjustment_policy_version == BENCHMARK_ADJUSTMENT_POLICY_VERSION
    assert result.manifest.source_batch_ids == ("raw-benchmark-batch",)
    bars = CanonicalDailyBarStore(tmp_path).load(DATASET)
    assert {bar.instrument_id for bar in bars} == {INSTRUMENT}
    assert {bar.dataset_version for bar in bars} == {DATASET}
    assert all(bar.close_split_adjusted == bar.close_raw for bar in bars)


def test_benchmark_missing_expected_exchange_session_fails_closed(tmp_path: Path) -> None:
    rows = _rows()
    del rows[2]

    with pytest.raises(TiingoBenchmarkPromotionError, match="session completeness failed"):
        promote_tiingo_benchmark_rows(
            rows,
            definition=_definition(),
            canonical_root=tmp_path,
            source_batch_ids=("raw-benchmark-batch",),
        )


def test_benchmark_rejects_eligible_adjusted_cross_check_disagreement(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["adjClose"] = 999.0

    with pytest.raises(TiingoBenchmarkPromotionError, match="adjusted cross-check"):
        promote_tiingo_benchmark_rows(
            rows,
            definition=_definition(),
            canonical_root=tmp_path,
            source_batch_ids=("raw-benchmark-batch",),
        )


def test_benchmark_requires_explicit_raw_batch_provenance(tmp_path: Path) -> None:
    with pytest.raises(TiingoBenchmarkPromotionError, match="source batch IDs"):
        promote_tiingo_benchmark_rows(
            _rows(),
            definition=_definition(),
            canonical_root=tmp_path,
            source_batch_ids=(),
        )
