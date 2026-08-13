"""Bind complete validation review bundles to explicit research decisions.

This module verifies that a research decision cites the review-ready validation evidence it claims to
use. It never infers a decision state from statistical results and it never promotes a subject.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.experiments.decision_evidence import VerifiedResearchDecisionLedger
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionError
from trade_scout.validation.reporting import ValidationReviewBundle

_VALIDATION_REVIEW_PREFIX = "validation-review:"


def validation_review_reference(bundle: ValidationReviewBundle) -> str:
    """Return the canonical evidence reference for one validation review bundle."""

    return f"{_VALIDATION_REVIEW_PREFIX}{bundle.report.report_id}"


@dataclass(frozen=True, slots=True)
class ValidationDecisionReviewEvidence:
    """Admissibility assessment for one validation review cited by a research decision."""

    reference: str
    report_id: str
    experiment_id: str
    validation_plan_id: str
    primary_outcome: str
    evidence_count: int
    warning_count: int
    completeness_verified: bool
    experiment_cited: bool
    reference_cited: bool
    detail: str

    @property
    def admissible(self) -> bool:
        """Return true only when the review bundle is complete and explicitly cited."""

        return self.completeness_verified and self.experiment_cited and self.reference_cited


@dataclass(frozen=True, slots=True)
class ValidationDecisionEvidenceReport:
    """Validation-review evidence assessment for one explicit research decision."""

    decision_id: str
    reviews: tuple[ValidationDecisionReviewEvidence, ...]
    unresolved_references: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        """Return true when every supplied/cited validation review is resolved and admissible."""

        return (
            bool(self.reviews)
            and all(review.admissible for review in self.reviews)
            and not self.unresolved_references
        )

    def require_verified(self) -> None:
        """Fail closed before governance records a decision with incomplete review evidence."""

        if self.verified:
            return
        failures = [review.detail for review in self.reviews if not review.admissible]
        if self.unresolved_references:
            failures.append(f"unresolved references={list(self.unresolved_references)!r}")
        if not self.reviews:
            failures.append("no validation review bundles supplied")
        raise ResearchDecisionError(
            "validation review evidence verification failed for "
            f"{self.decision_id}: {'; '.join(failures)}"
        )


def audit_validation_decision_evidence(
    decision: ResearchDecision,
    bundles: tuple[ValidationReviewBundle, ...],
) -> ValidationDecisionEvidenceReport:
    """Verify explicit linkage from a decision to complete validation review bundles."""

    report_ids = [bundle.report.report_id for bundle in bundles]
    if len(report_ids) != len(set(report_ids)):
        raise ValueError("validation review report IDs must be unique for one decision audit")

    cited_validation_references = tuple(
        reference
        for reference in decision.evidence_references
        if reference.startswith(_VALIDATION_REVIEW_PREFIX)
    )
    if len(cited_validation_references) != len(set(cited_validation_references)):
        raise ValueError("validation review evidence references must be unique")

    supplied_references = {validation_review_reference(bundle) for bundle in bundles}
    unresolved = tuple(sorted(set(cited_validation_references) - supplied_references))

    reviews: list[ValidationDecisionReviewEvidence] = []
    for bundle in bundles:
        reference = validation_review_reference(bundle)
        report = bundle.report
        complete = bundle.completeness.complete
        experiment_cited = report.experiment_id in decision.experiment_ids
        reference_cited = reference in decision.evidence_references
        detail_parts = []
        if not complete:
            detail_parts.append("review completeness is not verified")
        if not experiment_cited:
            detail_parts.append(f"experiment {report.experiment_id!r} is not cited by decision")
        if not reference_cited:
            detail_parts.append(f"evidence reference {reference!r} is not cited by decision")
        detail = "verified complete validation review" if not detail_parts else ", ".join(detail_parts)
        warning_count = sum(len(snapshot.warnings) for snapshot in report.snapshots)
        reviews.append(
            ValidationDecisionReviewEvidence(
                reference=reference,
                report_id=report.report_id,
                experiment_id=report.experiment_id,
                validation_plan_id=report.validation_plan_id,
                primary_outcome=report.primary_outcome,
                evidence_count=len(report.snapshots),
                warning_count=warning_count,
                completeness_verified=complete,
                experiment_cited=experiment_cited,
                reference_cited=reference_cited,
                detail=detail,
            )
        )

    return ValidationDecisionEvidenceReport(
        decision_id=decision.decision_id,
        reviews=tuple(reviews),
        unresolved_references=unresolved,
    )


class ValidationGovernedResearchDecisionLedger:
    """Decision-ledger decorator requiring both experiment and validation-review evidence."""

    def __init__(self, ledger: VerifiedResearchDecisionLedger) -> None:
        self._ledger = ledger

    def append(
        self,
        decision: ResearchDecision,
        *,
        validation_reviews: tuple[ValidationReviewBundle, ...],
    ) -> str:
        """Verify review evidence, then delegate experiment verification and immutable append."""

        audit_validation_decision_evidence(decision, validation_reviews).require_verified()
        return self._ledger.append(decision)

    def read(self, decision_id: str) -> ResearchDecision:
        """Delegate checksum-verified decision reads."""

        return self._ledger.read(decision_id)

    def history(self, subject_id: str) -> tuple[ResearchDecision, ...]:
        """Delegate subject history reconstruction."""

        return self._ledger.history(subject_id)

    def current(self, subject_id: str) -> ResearchDecision | None:
        """Delegate current-decision lookup."""

        return self._ledger.current(subject_id)
