"""Require cryptographic validation provenance at the research-decision boundary.

This module is the strictest validation-governance decorator. A research decision may cite a
persisted validation review only when that review is checksum-valid, has an immutable provenance
record, and the provenance can be reproduced from the supplied frozen validation design and source
experiment manifest. Scientific interpretation remains outside this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trade_scout.experiments.contracts import ExperimentManifest
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionError
from trade_scout.experiments.validation_decision_evidence import (
    ValidationGovernedResearchDecisionLedger,
    resolve_persisted_validation_reviews,
)
from trade_scout.experiments.validation_provenance import (
    FileValidationReviewProvenanceStore,
    ValidationReviewProvenance,
    ValidationReviewProvenanceError,
    verify_validation_review_provenance,
)
from trade_scout.validation.contracts import ValidationPlan
from trade_scout.validation.reporting import ValidationReviewBundle
from trade_scout.validation.robustness import RobustnessPlan
from trade_scout.validation.store import FileValidationReviewStore


class ValidationPlanReader(Protocol):
    """Read one frozen validation design by immutable identity."""

    def read_validation_plan(self, plan_id: str) -> ValidationPlan: ...


class ExperimentManifestReader(Protocol):
    """Read one checksum-verified experiment manifest by immutable identity."""

    def read_manifest(self, experiment_id: str) -> ExperimentManifest: ...


class RobustnessPlanReader(Protocol):
    """Read one frozen robustness design by immutable identity."""

    def read_robustness_plan(self, plan_id: str) -> RobustnessPlan: ...


@dataclass(frozen=True, slots=True)
class ProvenanceVerifiedValidationReview:
    """One persisted validation review whose full design/source lineage reproduced exactly."""

    report_id: str
    review_checksum: str
    provenance_checksum: str
    validation_plan_id: str
    validation_plan_checksum: str
    experiment_id: str
    experiment_manifest_checksum: str
    robustness_plan_id: str | None
    bundle: ValidationReviewBundle

    def __post_init__(self) -> None:
        if self.bundle.report.report_id != self.report_id:
            raise ValueError("verified validation review report identity does not match bundle")
        if self.bundle.report.validation_plan_id != self.validation_plan_id:
            raise ValueError("verified validation review plan identity does not match bundle")
        if self.bundle.report.experiment_id != self.experiment_id:
            raise ValueError("verified validation review experiment identity does not match bundle")
        for label, checksum in (
            ("review_checksum", self.review_checksum),
            ("provenance_checksum", self.provenance_checksum),
            ("validation_plan_checksum", self.validation_plan_checksum),
            ("experiment_manifest_checksum", self.experiment_manifest_checksum),
        ):
            if len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum
            ):
                raise ValueError(f"{label} must be a lowercase SHA-256 hexadecimal digest")


def resolve_provenance_verified_validation_reviews(
    decision: ResearchDecision,
    *,
    review_store: FileValidationReviewStore,
    provenance_store: FileValidationReviewProvenanceStore,
    validation_plan_reader: ValidationPlanReader,
    experiment_manifest_reader: ExperimentManifestReader,
    robustness_plan_reader: RobustnessPlanReader | None = None,
) -> tuple[ProvenanceVerifiedValidationReview, ...]:
    """Resolve every cited review and reproduce its cryptographic lineage fail closed."""

    persisted = resolve_persisted_validation_reviews(decision, review_store)
    verified: list[ProvenanceVerifiedValidationReview] = []
    for item in persisted:
        try:
            provenance = provenance_store.read(item.report_id)
            provenance_checksum = provenance_store.checksum(item.report_id)
            _require_reference_identity(item.bundle, provenance)
            plan = validation_plan_reader.read_validation_plan(provenance.validation_plan_id)
            manifest = experiment_manifest_reader.read_manifest(provenance.experiment_id)
            robustness_plan = _resolve_robustness_plan(
                provenance,
                robustness_plan_reader=robustness_plan_reader,
            )
            bundle = verify_validation_review_provenance(
                provenance,
                review_store=review_store,
                plan=plan,
                experiment_manifest=manifest,
                robustness_plan=robustness_plan,
            )
        except (ValidationReviewProvenanceError, KeyError, OSError, TypeError, ValueError) as exc:
            raise ResearchDecisionError(
                "validation review provenance verification failed for "
                f"validation-review:{item.report_id}: {exc}"
            ) from exc
        verified.append(
            ProvenanceVerifiedValidationReview(
                report_id=item.report_id,
                review_checksum=item.checksum,
                provenance_checksum=provenance_checksum,
                validation_plan_id=provenance.validation_plan_id,
                validation_plan_checksum=provenance.validation_plan_checksum,
                experiment_id=provenance.experiment_id,
                experiment_manifest_checksum=provenance.experiment_manifest_checksum,
                robustness_plan_id=provenance.robustness_plan_id,
                bundle=bundle,
            )
        )
    return tuple(verified)


def _require_reference_identity(
    bundle: ValidationReviewBundle,
    provenance: ValidationReviewProvenance,
) -> None:
    if provenance.report_id != bundle.report.report_id:
        raise ValidationReviewProvenanceError("provenance report identity does not match review")
    if provenance.validation_plan_id != bundle.report.validation_plan_id:
        raise ValidationReviewProvenanceError(
            "provenance validation plan identity does not match review"
        )
    if provenance.experiment_id != bundle.report.experiment_id:
        raise ValidationReviewProvenanceError(
            "provenance experiment identity does not match review"
        )
    if provenance.robustness_plan_id != bundle.robustness_plan_id:
        raise ValidationReviewProvenanceError(
            "provenance robustness plan identity does not match review"
        )


def _resolve_robustness_plan(
    provenance: ValidationReviewProvenance,
    *,
    robustness_plan_reader: RobustnessPlanReader | None,
) -> RobustnessPlan | None:
    plan_id = provenance.robustness_plan_id
    if plan_id is None:
        return None
    if robustness_plan_reader is None:
        raise ValidationReviewProvenanceError(
            f"robustness plan reader is required for provenance-bound plan {plan_id!r}"
        )
    return robustness_plan_reader.read_robustness_plan(plan_id)


class ProvenanceGovernedResearchDecisionLedger:
    """Decision ledger requiring persisted review, provenance, design, and experiment integrity."""

    def __init__(
        self,
        ledger: ValidationGovernedResearchDecisionLedger,
        *,
        review_store: FileValidationReviewStore,
        provenance_store: FileValidationReviewProvenanceStore,
        validation_plan_reader: ValidationPlanReader,
        experiment_manifest_reader: ExperimentManifestReader,
        robustness_plan_reader: RobustnessPlanReader | None = None,
    ) -> None:
        self._ledger = ledger
        self._review_store = review_store
        self._provenance_store = provenance_store
        self._validation_plan_reader = validation_plan_reader
        self._experiment_manifest_reader = experiment_manifest_reader
        self._robustness_plan_reader = robustness_plan_reader

    def append(self, decision: ResearchDecision) -> str:
        """Verify full review provenance before any downstream governance mutation occurs."""

        verified = resolve_provenance_verified_validation_reviews(
            decision,
            review_store=self._review_store,
            provenance_store=self._provenance_store,
            validation_plan_reader=self._validation_plan_reader,
            experiment_manifest_reader=self._experiment_manifest_reader,
            robustness_plan_reader=self._robustness_plan_reader,
        )
        return self._ledger.append(
            decision,
            validation_reviews=tuple(item.bundle for item in verified),
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
