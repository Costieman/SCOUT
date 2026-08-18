from __future__ import annotations

from pathlib import Path

from trade_scout.app.research_brain_evidence import (
    BrainEvidenceCoverageState,
    ResearchBrainEvidenceService,
)
from trade_scout.validation.completeness import ValidationCompleteness
from trade_scout.validation.contracts import SampleAccounting
from trade_scout.validation.evidence import (
    ComparatorDefinition,
    ComparatorKind,
    ConfidenceInterval,
    EffectEstimate,
    EvidenceRole,
    EvidenceSnapshot,
    MetricEstimate,
    ValidationEvidenceReport,
)
from trade_scout.validation.reporting import ValidationReviewBundle, ValidationRoleCount
from trade_scout.validation.store import FileValidationReviewStore


def _snapshot(
    evidence_id: str,
    role: EvidenceRole,
    *,
    comparator: bool = False,
    uncertainty: bool = False,
) -> EvidenceSnapshot:
    interval = (
        ConfidenceInterval(lower=-0.01, upper=0.03, confidence_level=0.95, method="fixture")
        if uncertainty
        else None
    )
    sample = SampleAccounting(raw_event_count=120, unique_instrument_count=80)
    effects = (
        (
            EffectEstimate(
                effect_id=f"effect_{evidence_id}",
                metric="forward_return",
                estimate=0.01,
                units="decimal_return",
                comparator=ComparatorDefinition(
                    comparator_id="trend_control",
                    kind=ComparatorKind.TREND_MATCHED,
                    description="Fixed trend-matched comparator fixture.",
                ),
                sample=sample,
                interval=interval,
            ),
        )
        if comparator
        else ()
    )
    return EvidenceSnapshot(
        evidence_id=evidence_id,
        role=role,
        sample=sample,
        metrics=(
            MetricEstimate(
                metric="forward_return",
                estimate=0.02,
                units="decimal_return",
                interval=interval,
            ),
        ),
        effects=effects,
        fold_id="fold_1" if role is EvidenceRole.WALK_FORWARD else None,
        challenge_id="nearby_parameter" if role is EvidenceRole.ROBUSTNESS else None,
    )


def _write_review(
    root: Path,
    *,
    report_id: str,
    experiment_id: str,
    snapshots: tuple[EvidenceSnapshot, ...],
    robustness: bool = False,
) -> None:
    role_counts = tuple(
        ValidationRoleCount(role=role, count=sum(item.role is role for item in snapshots))
        for role in EvidenceRole
    )
    bundle = ValidationReviewBundle(
        report=ValidationEvidenceReport(
            report_id=report_id,
            experiment_id=experiment_id,
            validation_plan_id=f"plan_{report_id}",
            primary_outcome="forward_return",
            snapshots=snapshots,
        ),
        assignments=(),
        completeness=ValidationCompleteness(
            complete=True,
            missing_targets=(),
            unexpected_targets=(),
            role_mismatches=(),
            unassigned_evidence=(),
        ),
        role_counts=role_counts,
        robustness_plan_id="robustness_v1" if robustness else None,
    )
    FileValidationReviewStore(root).write(bundle)


def test_exploratory_history_does_not_become_fake_validation(tmp_path: Path) -> None:
    service = ResearchBrainEvidenceService(tmp_path / "validation-reviews")

    coverage = service.experiment_coverage("exp_exploratory")
    summary = service.brain_summary(("exp_exploratory",))

    assert coverage.coverage_state is BrainEvidenceCoverageState.EXPLORATORY_ONLY
    assert coverage.report_ids == ()
    assert summary.reviewed_experiment_count == 0
    assert "exploratory history only" in summary.next_challenge
    assert "governed validation workflow" in summary.next_challenge


def test_governed_comparator_and_uncertainty_point_to_time_ordered_validation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "validation-reviews"
    _write_review(
        root,
        report_id="review_validation",
        experiment_id="exp_candidate",
        snapshots=(
            _snapshot(
                "validation_1",
                EvidenceRole.VALIDATION,
                comparator=True,
                uncertainty=True,
            ),
        ),
    )
    service = ResearchBrainEvidenceService(root)

    coverage = service.experiment_coverage("exp_candidate")
    summary = service.brain_summary(("exp_candidate",))

    assert coverage.coverage_state is BrainEvidenceCoverageState.VALIDATION_REVIEW_PRESENT
    assert coverage.comparator_kinds == (ComparatorKind.TREND_MATCHED,)
    assert coverage.has_uncertainty_intervals
    assert summary.validation_experiment_count == 1
    assert summary.walk_forward_experiment_count == 0
    assert "walk-forward evidence" in summary.next_challenge


def test_time_ordered_robustness_and_holdout_are_coverage_not_a_pass_decision(
    tmp_path: Path,
) -> None:
    root = tmp_path / "validation-reviews"
    _write_review(
        root,
        report_id="review_full",
        experiment_id="exp_frozen",
        snapshots=(
            _snapshot(
                "validation_1",
                EvidenceRole.VALIDATION,
                comparator=True,
                uncertainty=True,
            ),
            _snapshot("walk_1", EvidenceRole.WALK_FORWARD, comparator=True, uncertainty=True),
            _snapshot("robust_1", EvidenceRole.ROBUSTNESS, uncertainty=True),
            _snapshot("holdout_1", EvidenceRole.FINAL_HOLDOUT, comparator=True, uncertainty=True),
        ),
        robustness=True,
    )
    service = ResearchBrainEvidenceService(root)

    coverage = service.experiment_coverage("exp_frozen")
    summary = service.brain_summary(("exp_frozen",))

    assert coverage.coverage_state is BrainEvidenceCoverageState.FINAL_HOLDOUT_PRESENT
    assert coverage.has_robustness_evidence
    assert summary.walk_forward_experiment_count == 1
    assert summary.robustness_experiment_count == 1
    assert summary.final_holdout_experiment_count == 1
    assert "Review the explicit research decision" in summary.next_challenge
    assert "does not say that the strategy passed" in summary.interpretation_boundary


def test_unrelated_validation_reviews_do_not_upgrade_an_experiment(tmp_path: Path) -> None:
    root = tmp_path / "validation-reviews"
    _write_review(
        root,
        report_id="review_other",
        experiment_id="exp_other",
        snapshots=(_snapshot("validation_other", EvidenceRole.VALIDATION),),
    )
    service = ResearchBrainEvidenceService(root)

    coverage = service.experiment_coverage("exp_target")

    assert coverage.coverage_state is BrainEvidenceCoverageState.EXPLORATORY_ONLY
    assert coverage.report_ids == ()
