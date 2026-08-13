"""Bind complete validation review bundles to explicit research decisions.

This module verifies that a research decision cites the review-ready validation evidence that it
claims to use. It never infers a decision state from statistical results and it never promotes a
subject.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.experiments.decision_evidence import VerifiedResearchDecisionLedger
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionError
from trade_scout.validation.reporting import ValidationReviewBundle
from trade_scout.validation.store import FileValidationReviewStore, ValidationReviewStoreError

_VALIDATION_REVIEW_PREFIX = "validation-review:"


def validation_review_reference(bundle: ValidationReviewBundle) -> str:
    """Return the canonical evidence reference for one validation review bundle."""

    return f"{_VALIDATION_REVIEW_PREFIX}{bundle.report.report_id}"


def validation_review_report_id(reference: str) -> str | None:
    """Parse one canonical validation-review reference without accepting malformed IDs."""

    if not reference.startswith(_VALIDATION_REVIEW_PREFIX):
        return None
    report_id = reference.removeprefix(_VALIDATION_REVIEW_PREFIX)
    if not report_id or report_id != report_id.strip():
        raise ResearchDecisionError(f"malformed validation review reference: {reference!r}")
    if any(character in report_id for character in "/\\") or report_id in {".", ".."}:
        raise ResearchDecisionError(f"malformed validation review reference: {reference!r}")
    return report_id


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


@dataclass(frozen=True, slots=True)
class PersistedValidationReviewEvidence:
    """Checksum-verified persisted validation review resolved from a decision reference."""

    reference: str
    report_id: str
    checksum: str
    bundle: ValidationReviewBundle

    def __post_init__(self) -> None:
        if validation_review_reference(self.bundle) != self.reference:
            raise ValueError("persisted validation review reference does not match bundle identity")
        if self.bundle.report.report_id != self.report_id:
            raise ValueError("persisted validation review report ID does not match bundle identity")
        if len(self.checksum) != 64:
            raise ValueError("persisted validation review checksum must be SHA-256 hex length")


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
        detail = (
            "verified complete validation review" if not detail_parts else ", ".join(detail_parts)
        )
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


def resolve_persisted_validation_reviews(
    decision: ResearchDecision,
    store: FileValidationReviewStore,
) -> tuple[PersistedValidationReviewEvidence, ...]:
    """Resolve all validation references through checksum-verified immutable persistence."""

    references = tuple(
        reference
        for reference in decision.evidence_references
        if reference.startswith(_VALIDATION_REVIEW_PREFIX)
    )
    if not references:
        raise ResearchDecisionError(
            f"research decision {decision.decision_id} cites no persisted validation review"
        )
    if len(references) != len(set(references)):
        raise ResearchDecisionError("validation review evidence references must be unique")

    resolved: list[PersistedValidationReviewEvidence] = []
    for reference in references:
        report_id = validation_review_report_id(reference)
        if report_id is None:
            raise AssertionError("validation reference filter and parser disagree")
        try:
            bundle = store.read(report_id)
            checksum = store.checksum(report_id)
        except (ValidationReviewStoreError, ValueError) as exc:
            raise ResearchDecisionError(
                f"persisted validation review verification failed for {reference}: {exc}"
            ) from exc
        resolved.append(
            PersistedValidationReviewEvidence(
                reference=reference,
                report_id=report_id,
                checksum=checksum,
                bundle=bundle,
            )
        )
    return tuple(resolved)


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


class PersistedValidationGovernedResearchDecisionLedger:
    """Governance boundary that resolves validation evidence only from immutable persistence."""

    def __init__(
        self,
        ledger: ValidationGovernedResearchDecisionLedger,
        validation_store: FileValidationReviewStore,
    ) -> None:
        self._ledger = ledger
        self._validation_store = validation_store

    def append(self, decision: ResearchDecision) -> str:
        """Load and verify persisted reviews before the existing governance/experiment gates."""

        resolved = resolve_persisted_validation_reviews(decision, self._validation_store)
        return self._ledger.append(
            decision,
            validation_reviews=tuple(item.bundle for item in resolved),
        )

    def read(self, decision_id: str) -> ResearchDecision:
        """Delegate checksum-verified decision reads."""

        return self._ledger.read(decision_id)

    def history(self, subject_id: str) -> tuple[ResearchDecision, ...]:
        """Delegate subject history reconstruction."""

        return self._ledger.history(subject_id)

    def current(self, subject_id: str) -> ResearchDecision | None:
        """Delegate current-decision lookup."""

        return self._ledger.current(subject_id)
