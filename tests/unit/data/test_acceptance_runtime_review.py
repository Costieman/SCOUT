from __future__ import annotations

import hashlib
from pathlib import Path

from trade_scout.data.acceptance import (
    AcceptanceEvidence,
    AcceptanceEvidenceStatus,
    DataFoundationCriterion,
    evaluate_data_foundation_acceptance,
)
from trade_scout.data.acceptance_ledger import AcceptanceLedger
from trade_scout.data.acceptance_runtime_review import review_acceptance_runtime_evidence
from trade_scout.data.runtime_evidence import RuntimeEvidenceArtifact, RuntimeEvidenceRegistry


def _ledger() -> AcceptanceLedger:
    evidence = tuple(
        AcceptanceEvidence(
            criterion=criterion,
            status=(
                AcceptanceEvidenceStatus.PARTIAL
                if criterion is DataFoundationCriterion.CROSS_PROVIDER_VALIDATION
                else AcceptanceEvidenceStatus.DEMONSTRATED
            ),
            evidence=("fixture",),
            note="fixture evidence",
        )
        for criterion in DataFoundationCriterion
    )
    return AcceptanceLedger(
        assessment_version="fixture-v1",
        report=evaluate_data_foundation_acceptance(evidence),
    )


def test_review_verifies_runtime_artifacts_without_promoting_ledger(tmp_path: Path) -> None:
    payload = b"evidence\n"
    evidence_path = tmp_path / "cross-provider.json"
    evidence_path.write_bytes(payload)
    registry = RuntimeEvidenceRegistry(
        (
            RuntimeEvidenceArtifact(
                artifact_id="cross-provider",
                criterion=DataFoundationCriterion.CROSS_PROVIDER_VALIDATION,
                path=Path("cross-provider.json"),
                sha256=hashlib.sha256(payload).hexdigest(),
                producer="fixture",
            ),
        )
    )

    review = review_acceptance_runtime_evidence(_ledger(), registry, evidence_root=tmp_path)
    cross_provider = next(
        item
        for item in review.criteria
        if item.ledger_evidence.criterion is DataFoundationCriterion.CROSS_PROVIDER_VALIDATION
    )

    assert cross_provider.verified_runtime_artifact_count == 1
    assert cross_provider.ledger_evidence.status is AcceptanceEvidenceStatus.PARTIAL
    assert review.all_registered_runtime_evidence_verified is True


def test_review_fails_closed_for_unverified_registered_artifact(tmp_path: Path) -> None:
    registry = RuntimeEvidenceRegistry(
        (
            RuntimeEvidenceArtifact(
                artifact_id="missing",
                criterion=DataFoundationCriterion.STORAGE_BENCHMARK,
                path=Path("missing.json"),
                sha256="a" * 64,
                producer="fixture",
            ),
        )
    )

    review = review_acceptance_runtime_evidence(_ledger(), registry, evidence_root=tmp_path)
    benchmark = next(
        item
        for item in review.criteria
        if item.ledger_evidence.criterion is DataFoundationCriterion.STORAGE_BENCHMARK
    )

    assert benchmark.verified_runtime_artifact_count == 0
    assert benchmark.has_unverified_runtime_artifacts is True
    assert review.all_registered_runtime_evidence_verified is False
