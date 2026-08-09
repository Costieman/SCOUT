from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.data.provider_acceptance import (
    ProviderAcceptanceCriterion,
    ProviderAcceptanceError,
    ProviderAcceptanceEvidence,
    ProviderEvidenceStatus,
    evaluate_provider_acceptance,
    load_provider_acceptance,
)


def _all_demonstrated() -> tuple[ProviderAcceptanceEvidence, ...]:
    return tuple(
        ProviderAcceptanceEvidence(
            criterion=criterion,
            status=ProviderEvidenceStatus.DEMONSTRATED,
            evidence=(f"evidence/{criterion.value}.json",),
            note="reviewed evidence",
        )
        for criterion in ProviderAcceptanceCriterion
    )


def test_all_required_provider_criteria_are_needed_for_acceptance() -> None:
    report = evaluate_provider_acceptance("fixture", "v1", _all_demonstrated())

    assert report.accepted is True
    assert report.unresolved == ()
    assert len(report.evidence) == len(ProviderAcceptanceCriterion)


def test_partial_provider_evidence_blocks_acceptance() -> None:
    evidence = list(_all_demonstrated())
    evidence[0] = ProviderAcceptanceEvidence(
        criterion=evidence[0].criterion,
        status=ProviderEvidenceStatus.PARTIAL,
        evidence=("evidence/license-review.md",),
        note="rights not yet accepted",
    )

    report = evaluate_provider_acceptance("fixture", "v1", tuple(evidence))

    assert report.accepted is False
    assert report.unresolved == (evidence[0],)


def test_missing_provider_criterion_fails_closed() -> None:
    with pytest.raises(ProviderAcceptanceError, match="missing"):
        evaluate_provider_acceptance("fixture", "v1", _all_demonstrated()[:-1])


def test_demonstrated_provider_criterion_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.LICENSE_AND_RETENTION,
            status=ProviderEvidenceStatus.DEMONSTRATED,
            evidence=(),
            note="claimed without evidence",
        )


def test_checked_in_eodhd_assessment_remains_unaccepted() -> None:
    path = Path("configs/provider_acceptance_eodhd_v0.1.json")

    report = load_provider_acceptance(path)

    assert report.provider_id == "eodhd"
    assert report.accepted is False
    assert report.unresolved
    assert {item.criterion for item in report.evidence} == set(ProviderAcceptanceCriterion)
