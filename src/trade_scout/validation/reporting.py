"""Deterministic assembly of complete validation evidence for downstream review."""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.validation.completeness import (
    EvidenceAssignment,
    ValidationCompleteness,
    assess_validation_completeness,
)
from trade_scout.validation.contracts import ValidationPlan
from trade_scout.validation.evidence import EvidenceRole, ValidationEvidenceReport
from trade_scout.validation.multiplicity import AdjustedPValue, HypothesisFamily
from trade_scout.validation.parameter_surface import ParameterSurface
from trade_scout.validation.robustness import RobustnessPlan


@dataclass(frozen=True, slots=True)
class ValidationRoleCount:
    """Count of evidence snapshots retained for one validation role."""

    role: EvidenceRole
    count: int

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("validation role count must be non-negative")


@dataclass(frozen=True, slots=True)
class MultiplicitySummary:
    """Complete adjusted p-value family retained in the review bundle."""

    family: HypothesisFamily
    adjusted_values: tuple[AdjustedPValue, ...]

    def __post_init__(self) -> None:
        expected = tuple(self.family.hypothesis_ids)
        observed = tuple(item.hypothesis_id for item in self.adjusted_values)
        if observed != expected:
            raise ValueError(
                "adjusted p-values must preserve the registered hypothesis-family order exactly"
            )


@dataclass(frozen=True, slots=True)
class ValidationReviewBundle:
    """Complete evidence package ready for explicit scientific review.

    This object proves coverage and preserves supporting evidence metadata. It deliberately has no
    promotion status, pass/fail threshold, or strategy-selection field.
    """

    report: ValidationEvidenceReport
    assignments: tuple[EvidenceAssignment, ...]
    completeness: ValidationCompleteness
    role_counts: tuple[ValidationRoleCount, ...]
    parameter_surfaces: tuple[ParameterSurface, ...] = ()
    multiplicity: tuple[MultiplicitySummary, ...] = ()
    robustness_plan_id: str | None = None

    def __post_init__(self) -> None:
        if not self.completeness.complete:
            raise ValueError("validation review bundle requires complete evidence coverage")
        role_order = tuple(EvidenceRole)
        if tuple(item.role for item in self.role_counts) != role_order:
            raise ValueError("validation role counts must retain canonical EvidenceRole order")
        if len({surface.surface_id for surface in self.parameter_surfaces}) != len(
            self.parameter_surfaces
        ):
            raise ValueError("parameter surface IDs must be unique within a review bundle")
        family_ids = tuple(item.family.family_id for item in self.multiplicity)
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("multiplicity family IDs must be unique within a review bundle")
        expected_family = self.report.multiplicity_family_id
        if expected_family is not None and family_ids != (expected_family,):
            raise ValueError(
                "review bundle must contain exactly the multiplicity family declared by the report"
            )
        if expected_family is None and family_ids:
            raise ValueError(
                "multiplicity summaries require evidence report multiplicity_family_id to be declared"
            )
        if self.robustness_plan_id is not None and not self.robustness_plan_id.strip():
            raise ValueError("robustness_plan_id must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class ValidationReviewSummary:
    """Compact machine-readable inventory of a complete validation review bundle."""

    report_id: str
    experiment_id: str
    validation_plan_id: str
    primary_outcome: str
    evidence_count: int
    role_counts: tuple[ValidationRoleCount, ...]
    parameter_surface_ids: tuple[str, ...]
    multiplicity_family_ids: tuple[str, ...]
    robustness_plan_id: str | None
    warning_count: int


def assemble_validation_review_bundle(
    *,
    plan: ValidationPlan,
    report: ValidationEvidenceReport,
    assignments: tuple[EvidenceAssignment, ...],
    robustness_plan: RobustnessPlan | None = None,
    parameter_surfaces: tuple[ParameterSurface, ...] = (),
    multiplicity: tuple[MultiplicitySummary, ...] = (),
) -> ValidationReviewBundle:
    """Assemble one complete review package without inferring research status."""

    completeness = assess_validation_completeness(
        plan=plan,
        report=report,
        assignments=assignments,
        robustness_plan=robustness_plan,
    )
    completeness.require_complete()
    role_counts = tuple(
        ValidationRoleCount(role, len(report.snapshots_for(role))) for role in EvidenceRole
    )
    return ValidationReviewBundle(
        report=report,
        assignments=assignments,
        completeness=completeness,
        role_counts=role_counts,
        parameter_surfaces=parameter_surfaces,
        multiplicity=multiplicity,
        robustness_plan_id=robustness_plan.plan_id if robustness_plan is not None else None,
    )


def summarize_validation_review(bundle: ValidationReviewBundle) -> ValidationReviewSummary:
    """Return a deterministic inventory summary without collapsing evidence into one score."""

    warning_count = sum(len(snapshot.warnings) for snapshot in bundle.report.snapshots)
    return ValidationReviewSummary(
        report_id=bundle.report.report_id,
        experiment_id=bundle.report.experiment_id,
        validation_plan_id=bundle.report.validation_plan_id,
        primary_outcome=bundle.report.primary_outcome,
        evidence_count=len(bundle.report.snapshots),
        role_counts=bundle.role_counts,
        parameter_surface_ids=tuple(
            sorted(surface.surface_id for surface in bundle.parameter_surfaces)
        ),
        multiplicity_family_ids=tuple(
            sorted(item.family.family_id for item in bundle.multiplicity)
        ),
        robustness_plan_id=bundle.robustness_plan_id,
        warning_count=warning_count,
    )
