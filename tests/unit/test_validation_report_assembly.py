"""Tests for complete, non-promotional validation review bundle assembly."""

from datetime import date

import pytest

from trade_scout.validation import (
    AdjustedPValue,
    DateInterval,
    EvidenceAssignment,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceTargetKind,
    HypothesisFamily,
    IncompleteValidationEvidenceError,
    MetricEstimate,
    MultiplicityMethod,
    MultiplicitySummary,
    ParameterAxis,
    ParameterCell,
    ParameterSurface,
    SampleAccounting,
    ValidationEvidenceReport,
    ValidationReviewBundle,
    assemble_validation_review_bundle,
    build_fixed_holdout_plan,
    summarize_validation_review,
)


def _sample() -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=100,
        unique_instrument_count=60,
        effective_sample_size=55.0,
    )


def _snapshot(evidence_id: str, role: EvidenceRole, *, warning: str | None = None) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        evidence_id=evidence_id,
        role=role,
        sample=_sample(),
        metrics=(MetricEstimate("forward_return_60", 0.02, "fraction"),),
        warnings=(warning,) if warning is not None else (),
    )


def _plan():
    return build_fixed_holdout_plan(
        plan_id="plan-v1",
        development=DateInterval(date(2000, 1, 1), date(2010, 12, 31)),
        validation=DateInterval(date(2011, 1, 1), date(2018, 12, 31)),
        holdout=DateInterval(date(2019, 1, 1), date(2025, 12, 31)),
        primary_outcome="forward_return_60",
    )


def _assignments() -> tuple[EvidenceAssignment, ...]:
    return (
        EvidenceAssignment("development", EvidenceTargetKind.SEGMENT, "development"),
        EvidenceAssignment("validation", EvidenceTargetKind.SEGMENT, "validation"),
        EvidenceAssignment("holdout", EvidenceTargetKind.SEGMENT, "holdout"),
    )


def _surface() -> ParameterSurface:
    return ParameterSurface(
        surface_id="duration-surface",
        axes=(ParameterAxis("duration", (20, 30)),),
        metric="forward_return_60",
        units="fraction",
        cells=(
            ParameterCell(
                coordinates=(("duration", 20),),
                metric="forward_return_60",
                estimate=0.01,
                units="fraction",
                sample=_sample(),
            ),
            ParameterCell(
                coordinates=(("duration", 30),),
                metric="forward_return_60",
                estimate=0.02,
                units="fraction",
                sample=_sample(),
            ),
        ),
    )


def _multiplicity() -> MultiplicitySummary:
    family = HypothesisFamily(
        family_id="duration-family",
        hypothesis_ids=("duration-20", "duration-30"),
        method=MultiplicityMethod.BONFERRONI,
    )
    return MultiplicitySummary(
        family=family,
        adjusted_values=(
            AdjustedPValue("duration-20", 0.02, 0.04),
            AdjustedPValue("duration-30", 0.03, 0.06),
        ),
    )


def test_review_bundle_requires_complete_validation_coverage() -> None:
    plan = _plan()
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(
            _snapshot("development", EvidenceRole.DEVELOPMENT),
            _snapshot("validation", EvidenceRole.VALIDATION),
        ),
    )

    with pytest.raises(IncompleteValidationEvidenceError, match="SEGMENT:holdout"):
        assemble_validation_review_bundle(
            plan=plan,
            report=report,
            assignments=_assignments()[:2],
        )


def test_review_bundle_preserves_surfaces_multiplicity_and_role_counts() -> None:
    plan = _plan()
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        multiplicity_family_id="duration-family",
        snapshots=(
            _snapshot("development", EvidenceRole.DEVELOPMENT),
            _snapshot("validation", EvidenceRole.VALIDATION, warning="low effective sample"),
            _snapshot("holdout", EvidenceRole.FINAL_HOLDOUT),
        ),
    )

    bundle = assemble_validation_review_bundle(
        plan=plan,
        report=report,
        assignments=_assignments(),
        parameter_surfaces=(_surface(),),
        multiplicity=(_multiplicity(),),
    )
    summary = summarize_validation_review(bundle)

    assert bundle.completeness.complete
    assert summary.evidence_count == 3
    assert summary.parameter_surface_ids == ("duration-surface",)
    assert summary.multiplicity_family_ids == ("duration-family",)
    assert summary.warning_count == 1
    counts = {item.role: item.count for item in summary.role_counts}
    assert counts[EvidenceRole.DEVELOPMENT] == 1
    assert counts[EvidenceRole.VALIDATION] == 1
    assert counts[EvidenceRole.FINAL_HOLDOUT] == 1
    assert counts[EvidenceRole.WALK_FORWARD] == 0
    assert counts[EvidenceRole.ROBUSTNESS] == 0


def test_review_bundle_rejects_unregistered_multiplicity_summary() -> None:
    plan = _plan()
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(
            _snapshot("development", EvidenceRole.DEVELOPMENT),
            _snapshot("validation", EvidenceRole.VALIDATION),
            _snapshot("holdout", EvidenceRole.FINAL_HOLDOUT),
        ),
    )

    with pytest.raises(ValueError, match="multiplicity summaries require"):
        assemble_validation_review_bundle(
            plan=plan,
            report=report,
            assignments=_assignments(),
            multiplicity=(_multiplicity(),),
        )


def test_multiplicity_summary_requires_exact_hypothesis_order() -> None:
    family = HypothesisFamily(
        family_id="duration-family",
        hypothesis_ids=("duration-20", "duration-30"),
        method=MultiplicityMethod.BONFERRONI,
    )

    with pytest.raises(ValueError, match="preserve the registered"):
        MultiplicitySummary(
            family=family,
            adjusted_values=(
                AdjustedPValue("duration-30", 0.03, 0.06),
                AdjustedPValue("duration-20", 0.02, 0.04),
            ),
        )


def test_review_bundle_itself_cannot_be_built_from_incomplete_assessment() -> None:
    plan = _plan()
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(
            _snapshot("development", EvidenceRole.DEVELOPMENT),
            _snapshot("validation", EvidenceRole.VALIDATION),
            _snapshot("holdout", EvidenceRole.FINAL_HOLDOUT),
        ),
    )
    bundle = assemble_validation_review_bundle(
        plan=plan,
        report=report,
        assignments=_assignments(),
    )

    with pytest.raises(ValueError, match="requires complete evidence"):
        ValidationReviewBundle(
            report=bundle.report,
            assignments=bundle.assignments,
            completeness=type(bundle.completeness)(
                complete=False,
                missing_targets=("SEGMENT:holdout",),
                unexpected_targets=(),
                role_mismatches=(),
                unassigned_evidence=(),
            ),
            role_counts=bundle.role_counts,
        )
