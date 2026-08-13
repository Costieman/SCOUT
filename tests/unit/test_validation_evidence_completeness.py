"""Tests for fail-closed coverage of frozen validation designs."""

from datetime import date

import pytest

from trade_scout.validation import (
    DateInterval,
    EvidenceAssignment,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceTargetKind,
    IncompleteValidationEvidenceError,
    MetricEstimate,
    RobustnessChallenge,
    RobustnessKind,
    RobustnessPlan,
    SampleAccounting,
    ValidationEvidenceReport,
    assess_validation_completeness,
    build_fixed_holdout_plan,
    build_walk_forward_plan,
)


def _sample() -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=100,
        unique_instrument_count=70,
        effective_sample_size=60.0,
    )


def _snapshot(
    evidence_id: str,
    role: EvidenceRole,
    *,
    fold_id: str | None = None,
    challenge_id: str | None = None,
) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        evidence_id=evidence_id,
        role=role,
        sample=_sample(),
        metrics=(MetricEstimate("forward_return_60", 0.02, "fraction"),),
        fold_id=fold_id,
        challenge_id=challenge_id,
    )


def test_complete_fixed_holdout_bundle_passes_exact_coverage_gate() -> None:
    plan = build_fixed_holdout_plan(
        plan_id="fixed-v1",
        development=DateInterval(date(2000, 1, 1), date(2010, 12, 31)),
        validation=DateInterval(date(2011, 1, 1), date(2018, 12, 31)),
        holdout=DateInterval(date(2019, 1, 1), date(2025, 12, 31)),
        primary_outcome="forward_return_60",
    )
    snapshots = (
        _snapshot("development-evidence", EvidenceRole.DEVELOPMENT),
        _snapshot("validation-evidence", EvidenceRole.VALIDATION),
        _snapshot("holdout-evidence", EvidenceRole.FINAL_HOLDOUT),
    )
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=snapshots,
    )
    assignments = (
        EvidenceAssignment(
            "development-evidence",
            EvidenceTargetKind.SEGMENT,
            "development",
        ),
        EvidenceAssignment("validation-evidence", EvidenceTargetKind.SEGMENT, "validation"),
        EvidenceAssignment("holdout-evidence", EvidenceTargetKind.SEGMENT, "holdout"),
    )

    assessment = assess_validation_completeness(
        plan=plan,
        report=report,
        assignments=assignments,
    )

    assert assessment.complete
    assessment.require_complete()


def test_missing_holdout_evidence_fails_closed() -> None:
    plan = build_fixed_holdout_plan(
        plan_id="fixed-v1",
        development=DateInterval(date(2000, 1, 1), date(2010, 12, 31)),
        validation=DateInterval(date(2011, 1, 1), date(2018, 12, 31)),
        holdout=DateInterval(date(2019, 1, 1), date(2025, 12, 31)),
        primary_outcome="forward_return_60",
    )
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(
            _snapshot("development-evidence", EvidenceRole.DEVELOPMENT),
            _snapshot("validation-evidence", EvidenceRole.VALIDATION),
        ),
    )
    assignments = (
        EvidenceAssignment(
            "development-evidence",
            EvidenceTargetKind.SEGMENT,
            "development",
        ),
        EvidenceAssignment("validation-evidence", EvidenceTargetKind.SEGMENT, "validation"),
    )

    assessment = assess_validation_completeness(
        plan=plan,
        report=report,
        assignments=assignments,
    )

    assert not assessment.complete
    assert assessment.missing_targets == ("SEGMENT:holdout",)
    with pytest.raises(IncompleteValidationEvidenceError, match="SEGMENT:holdout"):
        assessment.require_complete()


def test_walk_forward_folds_require_matching_fold_evidence() -> None:
    plan = build_walk_forward_plan(
        plan_id="walk-forward-v1",
        boundaries=(
            date(2000, 1, 1),
            date(2005, 1, 1),
            date(2010, 1, 1),
            date(2015, 1, 1),
        ),
        primary_outcome="forward_return_60",
    )
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(
            _snapshot("development", EvidenceRole.DEVELOPMENT),
            _snapshot("validation", EvidenceRole.VALIDATION),
            _snapshot("fold-01-evidence", EvidenceRole.WALK_FORWARD, fold_id="fold-01"),
            _snapshot("fold-02-evidence", EvidenceRole.WALK_FORWARD, fold_id="fold-02"),
        ),
    )
    assignments = (
        EvidenceAssignment(
            "development",
            EvidenceTargetKind.SEGMENT,
            "walk-forward-development-envelope",
        ),
        EvidenceAssignment(
            "validation",
            EvidenceTargetKind.SEGMENT,
            "walk-forward-final-validation",
        ),
        EvidenceAssignment(
            "fold-01-evidence",
            EvidenceTargetKind.WALK_FORWARD_FOLD,
            "fold-01",
        ),
        EvidenceAssignment(
            "fold-02-evidence",
            EvidenceTargetKind.WALK_FORWARD_FOLD,
            "fold-02",
        ),
    )

    assessment = assess_validation_completeness(
        plan=plan,
        report=report,
        assignments=assignments,
    )

    assert assessment.complete


def test_robustness_plan_requires_every_predeclared_challenge() -> None:
    plan = build_fixed_holdout_plan(
        plan_id="fixed-v1",
        development=DateInterval(date(2000, 1, 1), date(2010, 12, 31)),
        validation=DateInterval(date(2011, 1, 1), date(2018, 12, 31)),
        primary_outcome="forward_return_60",
    )
    robustness = RobustnessPlan(
        plan_id="robustness-v1",
        challenges=(
            RobustnessChallenge(
                challenge_id="entry-shift",
                kind=RobustnessKind.ENTRY_SHIFT,
                description="Shift execution by one session.",
                changed_fields=("entry_convention",),
            ),
        ),
    )
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
    assignments = (
        EvidenceAssignment("development", EvidenceTargetKind.SEGMENT, "development"),
        EvidenceAssignment("validation", EvidenceTargetKind.SEGMENT, "validation"),
    )

    assessment = assess_validation_completeness(
        plan=plan,
        report=report,
        assignments=assignments,
        robustness_plan=robustness,
    )

    assert assessment.missing_targets == ("ROBUSTNESS_CHALLENGE:entry-shift",)


def test_evidence_cannot_be_reused_to_satisfy_two_targets() -> None:
    plan = build_fixed_holdout_plan(
        plan_id="fixed-v1",
        development=DateInterval(date(2000, 1, 1), date(2010, 12, 31)),
        validation=DateInterval(date(2011, 1, 1), date(2018, 12, 31)),
    )
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-1",
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(_snapshot("same", EvidenceRole.DEVELOPMENT),),
    )
    assignments = (
        EvidenceAssignment("same", EvidenceTargetKind.SEGMENT, "development"),
        EvidenceAssignment("same", EvidenceTargetKind.SEGMENT, "validation"),
    )

    with pytest.raises(ValueError, match="cannot satisfy multiple"):
        assess_validation_completeness(
            plan=plan,
            report=report,
            assignments=assignments,
        )
