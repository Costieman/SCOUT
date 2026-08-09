from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.acceptance import AcceptanceEvidenceStatus, DataFoundationCriterion
from trade_scout.data.evidence_bridge import RuntimeEvidenceError, assess_runtime_evidence


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_completed_listing_evidence_can_demonstrate_delistings(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "listing.json",
        {
            "evaluation_id": "alpha-vantage-live-evaluation-v0.3",
            "progress": {"complete": True},
            "listing_snapshots": [
                {"as_of": "2014-07-10", "delisted_count": 123},
                {"as_of": "latest", "delisted_count": 456},
            ],
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.criterion is DataFoundationCriterion.DELISTINGS
    assert result.evidence.status is AcceptanceEvidenceStatus.DEMONSTRATED


def test_partial_listing_run_remains_partial_even_with_delisted_rows(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "listing.json",
        {
            "evaluation_id": "alpha-vantage-live-evaluation-v0.3",
            "progress": {"complete": False},
            "listing_snapshots": [{"as_of": "2014-07-10", "delisted_count": 123}],
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_passing_historical_ohlcv_evidence_can_demonstrate_ingestion(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "ohlcv.json",
        {
            "provider_id": "fixture",
            "passed": True,
            "cases": [
                {
                    "case_id": "abc",
                    "observation_count": 250,
                    "first_trade_date": "2020-01-02",
                    "last_trade_date": "2020-12-31",
                }
            ],
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.criterion is DataFoundationCriterion.HISTORICAL_INGESTION
    assert result.evidence.status is AcceptanceEvidenceStatus.DEMONSTRATED


def test_failed_historical_ohlcv_evidence_remains_partial(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "ohlcv.json",
        {
            "provider_id": "fixture",
            "passed": False,
            "cases": [
                {
                    "case_id": "abc",
                    "observation_count": 250,
                    "first_trade_date": "2020-01-02",
                    "last_trade_date": "2020-12-31",
                }
            ],
        },
    )

    assert assess_runtime_evidence(path).evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_unknown_report_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path / "unknown.json", {"hello": "world"})

    with pytest.raises(RuntimeEvidenceError, match="unsupported"):
        assess_runtime_evidence(path)
