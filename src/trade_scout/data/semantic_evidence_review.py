"""Semantic review of integrity-verified Phase 1 runtime evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.acceptance import AcceptanceEvidenceStatus, DataFoundationCriterion
from trade_scout.data.evidence_bridge import RuntimeEvidenceError, assess_runtime_evidence
from trade_scout.data.runtime_evidence import RuntimeEvidenceArtifact, RuntimeEvidenceRegistry


@dataclass(frozen=True, slots=True)
class SemanticRuntimeEvidenceReview:
    """Integrity and semantic assessment for one registered runtime artifact."""

    artifact: RuntimeEvidenceArtifact
    integrity_verified: bool
    semantic_status: AcceptanceEvidenceStatus | None
    semantic_note: str | None
    assessment_error: str | None

    @property
    def is_promotion_candidate(self) -> bool:
        """Return true only for verified evidence whose semantics support demonstration."""

        return (
            self.integrity_verified
            and self.semantic_status is AcceptanceEvidenceStatus.DEMONSTRATED
            and self.assessment_error is None
        )


@dataclass(frozen=True, slots=True)
class SemanticRuntimeEvidenceReport:
    """Batch semantic review without mutating the checked-in acceptance ledger."""

    reviews: tuple[SemanticRuntimeEvidenceReview, ...]

    @property
    def has_invalid_evidence(self) -> bool:
        return any(
            not review.integrity_verified or review.assessment_error for review in self.reviews
        )

    def promotion_candidates(
        self,
        criterion: DataFoundationCriterion | None = None,
    ) -> tuple[SemanticRuntimeEvidenceReview, ...]:
        return tuple(
            review
            for review in self.reviews
            if review.is_promotion_candidate
            and (criterion is None or review.artifact.criterion is criterion)
        )


def review_semantic_runtime_evidence(
    registry: RuntimeEvidenceRegistry,
    *,
    evidence_root: Path,
) -> SemanticRuntimeEvidenceReport:
    """Verify bytes, assess known report semantics, and reject criterion mismatches."""

    reviews: list[SemanticRuntimeEvidenceReview] = []
    for verification in registry.verify(evidence_root):
        artifact = verification.artifact
        if not verification.verified:
            reviews.append(
                SemanticRuntimeEvidenceReview(
                    artifact=artifact,
                    integrity_verified=False,
                    semantic_status=None,
                    semantic_note=None,
                    assessment_error="runtime evidence failed integrity verification",
                )
            )
            continue

        source_path = evidence_root / artifact.path
        try:
            assessment = assess_runtime_evidence(source_path)
        except RuntimeEvidenceError as exc:
            reviews.append(
                SemanticRuntimeEvidenceReview(
                    artifact=artifact,
                    integrity_verified=True,
                    semantic_status=None,
                    semantic_note=None,
                    assessment_error=str(exc),
                )
            )
            continue

        if assessment.evidence.criterion is not artifact.criterion:
            reviews.append(
                SemanticRuntimeEvidenceReview(
                    artifact=artifact,
                    integrity_verified=True,
                    semantic_status=None,
                    semantic_note=None,
                    assessment_error=(
                        "registered criterion does not match the runtime report's semantic criterion"
                    ),
                )
            )
            continue

        reviews.append(
            SemanticRuntimeEvidenceReview(
                artifact=artifact,
                integrity_verified=True,
                semantic_status=assessment.evidence.status,
                semantic_note=assessment.evidence.note,
                assessment_error=None,
            )
        )

    return SemanticRuntimeEvidenceReport(reviews=tuple(reviews))
