from __future__ import annotations

import pytest

from trade_scout.data.acceptance import (
    AcceptanceEvidence,
    AcceptanceEvidenceStatus,
    DataFoundationCriterion,
    DataFoundationIncompleteError,
    evaluate_data_foundation_acceptance,
)


def _evidence(
    *,
    override: dict[DataFoundationCriterion, AcceptanceEvidenceStatus] | None = None,
) -> tuple[AcceptanceEvidence, ...]:
    statuses = override or {}
    return tuple(
        AcceptanceEvidence(
            criterion=criterion,
            status=statuses.get(criterion, AcceptanceEvidenceStatus.DEMONSTRATED),
            evidence=(f"tests/evidence/{criterion.value}",),
            note="Deterministic acceptance evidence.",
        )
        for criterion in DataFoundationCriterion
    )


def test_complete_report_passes_gate_only_when_every_criterion_is_demonstrated() -> None:
    report = evaluate_data_foundation_acceptance(_evidence())

    assert report.phase_complete is True
    assert report.unresolved == ()
    report.require_complete()


def test_partial_criterion_blocks_phase_exit() -> None:
    report = evaluate_data_foundation_acceptance(
        _evidence(
            override={
                DataFoundationCriterion.HISTORICAL_INGESTION: AcceptanceEvidenceStatus.PARTIAL
            }
        )
    )

    assert report.phase_complete is False
    assert [item.criterion for item in report.unresolved] == [
        DataFoundationCriterion.HISTORICAL_INGESTION
    ]
    with pytest.raises(DataFoundationIncompleteError, match="reproducible_historical_ohlcv"):
        report.require_complete()


def test_missing_criterion_is_invalid_assessment_not_implicit_failure() -> None:
    evidence = tuple(
        item
        for item in _evidence()
        if item.criterion is not DataFoundationCriterion.STORAGE_BENCHMARK
    )

    with pytest.raises(ValueError, match="representative_parquet_duckdb_benchmark"):
        evaluate_data_foundation_acceptance(evidence)


def test_duplicate_criterion_is_rejected() -> None:
    evidence = _evidence()

    with pytest.raises(ValueError, match="duplicate acceptance evidence"):
        evaluate_data_foundation_acceptance((*evidence, evidence[0]))


def test_demonstrated_status_requires_artifact_reference() -> None:
    with pytest.raises(ValueError, match="cite at least one artifact"):
        AcceptanceEvidence(
            criterion=DataFoundationCriterion.DATA_QUALITY,
            status=AcceptanceEvidenceStatus.DEMONSTRATED,
            evidence=(),
            note="Claim without evidence must fail.",
        )
