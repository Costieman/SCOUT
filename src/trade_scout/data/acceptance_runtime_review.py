"""Join the checked-in Phase 1 ledger with verified local runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.acceptance import AcceptanceEvidence, DataFoundationCriterion
from trade_scout.data.acceptance_ledger import AcceptanceLedger
from trade_scout.data.runtime_evidence import RuntimeEvidenceRegistry, RuntimeEvidenceVerification


@dataclass(frozen=True, slots=True)
class CriterionRuntimeEvidenceReview:
    """Ledger state plus integrity verification for one acceptance criterion."""

    ledger_evidence: AcceptanceEvidence
    runtime_verifications: tuple[RuntimeEvidenceVerification, ...]

    @property
    def verified_runtime_artifact_count(self) -> int:
        return sum(item.verified for item in self.runtime_verifications)

    @property
    def has_unverified_runtime_artifacts(self) -> bool:
        return any(not item.verified for item in self.runtime_verifications)


@dataclass(frozen=True, slots=True)
class AcceptanceRuntimeReview:
    """Evidence review that never mutates or promotes the checked-in ledger."""

    assessment_version: str
    criteria: tuple[CriterionRuntimeEvidenceReview, ...]

    @property
    def all_registered_runtime_evidence_verified(self) -> bool:
        verifications = tuple(
            verification
            for criterion in self.criteria
            for verification in criterion.runtime_verifications
        )
        return bool(verifications) and all(item.verified for item in verifications)


def review_acceptance_runtime_evidence(
    ledger: AcceptanceLedger,
    registry: RuntimeEvidenceRegistry,
    *,
    evidence_root: Path,
) -> AcceptanceRuntimeReview:
    """Verify registered runtime evidence alongside the ledger without inferring acceptance."""

    verified_by_criterion: dict[DataFoundationCriterion, list[RuntimeEvidenceVerification]] = {
        criterion: [] for criterion in DataFoundationCriterion
    }
    for verification in registry.verify(evidence_root):
        verified_by_criterion[verification.artifact.criterion].append(verification)

    return AcceptanceRuntimeReview(
        assessment_version=ledger.assessment_version,
        criteria=tuple(
            CriterionRuntimeEvidenceReview(
                ledger_evidence=item,
                runtime_verifications=tuple(verified_by_criterion[item.criterion]),
            )
            for item in ledger.report.evidence
        ),
    )
