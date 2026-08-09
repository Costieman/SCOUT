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


def test_cross_provider_report_requires_explicit_representative_acceptance(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "cross-provider.json",
        {
            "evaluation_id": "alpha-tiingo-cross-validation-v0.1",
            "expected_case_count": 3,
            "completed_case_count": 3,
            "complete": True,
            "unresolved_discrepancy_count": 0,
            "representative_sample_accepted": False,
            "cases": [{}, {}, {}],
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.criterion is DataFoundationCriterion.CROSS_PROVIDER_VALIDATION
    assert result.evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_reviewed_cross_provider_report_can_demonstrate_validation(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "cross-provider.json",
        {
            "evaluation_id": "alpha-tiingo-cross-validation-v0.1",
            "expected_case_count": 2,
            "completed_case_count": 2,
            "complete": True,
            "unresolved_discrepancy_count": 0,
            "representative_sample_accepted": True,
            "cases": [{}, {}],
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.status is AcceptanceEvidenceStatus.DEMONSTRATED


def test_cross_provider_report_with_unresolved_discrepancy_stays_partial(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "cross-provider.json",
        {
            "evaluation_id": "alpha-tiingo-cross-validation-v0.1",
            "expected_case_count": 2,
            "completed_case_count": 2,
            "complete": True,
            "unresolved_discrepancy_count": 1,
            "representative_sample_accepted": True,
            "cases": [{}, {}],
        },
    )

    assert assess_runtime_evidence(path).evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_storage_benchmark_requires_explicit_representative_acceptance(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "storage.json",
        {
            "dataset_version": "dataset-v1",
            "record_count": 1000,
            "unique_instrument_count": 5,
            "first_trade_date": "2020-01-02",
            "last_trade_date": "2022-12-30",
            "parquet_bytes": 10000,
            "filtered_query_count": 100,
            "representative_sample_accepted": False,
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.criterion is DataFoundationCriterion.STORAGE_BENCHMARK
    assert result.evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_reviewed_storage_benchmark_can_demonstrate_criterion(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "storage.json",
        {
            "dataset_version": "dataset-v1",
            "record_count": 1000,
            "unique_instrument_count": 5,
            "first_trade_date": "2020-01-02",
            "last_trade_date": "2022-12-30",
            "parquet_bytes": 10000,
            "filtered_query_count": 100,
            "representative_sample_accepted": True,
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.status is AcceptanceEvidenceStatus.DEMONSTRATED


def test_campaign_storage_evidence_can_demonstrate_benchmark(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "campaign-storage.json",
        {
            "schema_version": "eodhd-campaign-storage-evidence-v0.1",
            "dataset_version": "eodhd-representative-v1",
            "representative_sample_accepted": True,
            "representative_sample": {"failures": []},
            "storage_benchmark": {
                "record_count": 1_250_000,
                "unique_instrument_count": 525,
                "first_trade_date": "2018-01-02",
                "last_trade_date": "2025-12-31",
                "parquet_bytes": 50_000_000,
                "filtered_query_count": 250_000,
            },
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.criterion is DataFoundationCriterion.STORAGE_BENCHMARK
    assert result.evidence.status is AcceptanceEvidenceStatus.DEMONSTRATED


def test_campaign_storage_scope_failure_remains_partial_without_benchmark(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "campaign-storage.json",
        {
            "schema_version": "eodhd-campaign-storage-evidence-v0.1",
            "dataset_version": "eodhd-representative-v1",
            "representative_sample_accepted": False,
            "representative_sample": {"failures": ["record_count_below_minimum"]},
            "storage_benchmark": None,
        },
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_campaign_storage_evidence_rejects_contradictory_acceptance(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "campaign-storage.json",
        {
            "schema_version": "eodhd-campaign-storage-evidence-v0.1",
            "dataset_version": "eodhd-representative-v1",
            "representative_sample_accepted": True,
            "representative_sample": {"failures": ["exchange_count_below_minimum"]},
            "storage_benchmark": None,
        },
    )

    with pytest.raises(RuntimeEvidenceError, match="contradicts"):
        assess_runtime_evidence(path)


def test_unknown_report_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path / "unknown.json", {"hello": "world"})

    with pytest.raises(RuntimeEvidenceError, match="unsupported"):
        assess_runtime_evidence(path)
