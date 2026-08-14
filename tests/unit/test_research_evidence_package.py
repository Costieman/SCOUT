"""Tests for deterministic canonical research evidence packaging."""

from __future__ import annotations

from dataclasses import replace

import pytest

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
    StageRecord,
)
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionState
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
from trade_scout.validation.multiplicity import (
    AdjustedPValue,
    HypothesisFamily,
    MultiplicityMethod,
)
from trade_scout.validation.reporting import (
    MultiplicitySummary,
    ValidationReviewBundle,
    ValidationRoleCount,
)
from trade_scout.validation.research_package import (
    build_research_evidence_package,
    canonical_research_reporting_profile,
    summarize_research_evidence_package,
)


def _sample() -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=120,
        unique_instrument_count=80,
        effective_sample_size=63.5,
        cluster_count=18,
        exclusions=("7 events lacked complete forward history",),
    )


def _primary_metrics() -> tuple[MetricEstimate, ...]:
    interval = ConfidenceInterval(
        lower=0.51,
        upper=0.67,
        confidence_level=0.95,
        method="cluster-bootstrap",
    )
    values = (
        ("mean_outcome", 0.041),
        ("median_outcome", 0.028),
        ("expectancy", 0.041),
        ("return_quantile_p05", -0.18),
        ("return_quantile_p50", 0.028),
        ("return_quantile_p95", 0.29),
        ("mae_quantile_p10", -0.11),
        ("mae_quantile_p50", -0.045),
        ("mae_quantile_p90", -0.012),
        ("mfe_quantile_p10", 0.018),
        ("mfe_quantile_p50", 0.09),
        ("mfe_quantile_p90", 0.31),
    )
    metrics = [
        MetricEstimate(metric=name, estimate=value, units="return_fraction")
        for name, value in values
    ]
    metrics.insert(
        2,
        MetricEstimate(
            metric="win_probability",
            estimate=0.59,
            units="probability",
            interval=interval,
        ),
    )
    return tuple(metrics)


def _effect() -> EffectEstimate:
    comparator = ComparatorDefinition(
        comparator_id="same-trend-without-pattern",
        kind=ComparatorKind.TREND_MATCHED,
        description="Same trend context without the target consolidation pattern.",
        matching_fields=("trend_context", "signal_date_bucket"),
    )
    return EffectEstimate(
        effect_id="primary-comparator-effect",
        metric="forward_return",
        estimate=0.016,
        units="return_fraction",
        comparator=comparator,
        sample=_sample(),
        interval=ConfidenceInterval(
            lower=0.004,
            upper=0.029,
            confidence_level=0.95,
            method="cluster-bootstrap",
        ),
        p_value=0.012,
        adjusted_p_value=0.024,
    )


def _snapshot(
    evidence_id: str,
    role: EvidenceRole,
    *,
    fold_id: str | None = None,
    challenge_id: str | None = None,
    primary: bool = False,
) -> EvidenceSnapshot:
    metrics = (
        _primary_metrics()
        if primary
        else (MetricEstimate("mean_outcome", 0.03, "return_fraction"),)
    )
    effects = (_effect(),) if primary else ()
    return EvidenceSnapshot(
        evidence_id=evidence_id,
        role=role,
        sample=_sample(),
        metrics=metrics,
        effects=effects,
        fold_id=fold_id,
        challenge_id=challenge_id,
    )


def _review(*, primary_metrics: tuple[MetricEstimate, ...] | None = None) -> ValidationReviewBundle:
    primary = _snapshot("validation-primary", EvidenceRole.VALIDATION, primary=True)
    if primary_metrics is not None:
        primary = replace(primary, metrics=primary_metrics)
    snapshots = (
        primary,
        _snapshot("wf-1", EvidenceRole.WALK_FORWARD, fold_id="fold-1"),
        _snapshot(
            "robust-cost",
            EvidenceRole.ROBUSTNESS,
            challenge_id="higher-cost-stress",
        ),
        _snapshot("final-holdout", EvidenceRole.FINAL_HOLDOUT),
    )
    report = ValidationEvidenceReport(
        report_id="validation-report-v1",
        experiment_id="exp-confirmatory-001",
        validation_plan_id="validation-plan-v1",
        primary_outcome="forward_return_20_sessions",
        snapshots=snapshots,
        multiplicity_family_id="family-confirmatory-v1",
        notes=("Daily-bar ambiguity was retained where ordering was unknowable.",),
    )
    family = HypothesisFamily(
        family_id="family-confirmatory-v1",
        hypothesis_ids=("primary-effect",),
        method=MultiplicityMethod.BENJAMINI_HOCHBERG,
    )
    multiplicity = MultiplicitySummary(
        family=family,
        adjusted_values=(
            AdjustedPValue(
                hypothesis_id="primary-effect",
                raw_p_value=0.012,
                adjusted_p_value=0.012,
            ),
        ),
    )
    counts = {role: 0 for role in EvidenceRole}
    for snapshot in snapshots:
        counts[snapshot.role] += 1
    return ValidationReviewBundle(
        report=report,
        assignments=(),
        completeness=ValidationCompleteness(True, (), (), (), ()),
        role_counts=tuple(ValidationRoleCount(role, counts[role]) for role in EvidenceRole),
        multiplicity=(multiplicity,),
        robustness_plan_id="consolidation-breakout-v0.1",
    )


def _manifest() -> ExperimentManifest:
    definition = ExperimentDefinition(
        name="Experiment J walk-forward and final holdout",
        hypothesis="The frozen candidate retains comparator-adjusted effect on unseen data.",
        mode=ResearchMode.CONFIRMATORY,
        dataset_version="canonical-us-equity-v17",
        universe_version="pit-us-equity-v8",
        code_version="git:0123456789abcdef",
        config_schema_version="experiment-config-v0.1",
        resolved_configuration={
            "candidate_id": "consolidation-breakout-candidate-v1",
            "primary_horizon": 20,
        },
        hypothesis_family_id="consolidation-breakouts-v0.1:J",
        parent_experiment_id="exp-validation-000",
    )
    return ExperimentManifest(
        experiment_id="exp-confirmatory-001",
        definition=definition,
        status=ExperimentStatus.SUCCEEDED,
        created_at="2026-08-14T00:00:00+00:00",
        started_at="2026-08-14T00:01:00+00:00",
        completed_at="2026-08-14T00:10:00+00:00",
        stages=(
            StageRecord(
                stage_name="validation",
                started_at="2026-08-14T00:01:00+00:00",
                completed_at="2026-08-14T00:10:00+00:00",
                output_checksum="stage-output-checksum-v1",
                warnings=(),
            ),
        ),
        manifest_checksum="manifest-checksum-v1",
    )


def _decision() -> ResearchDecision:
    return ResearchDecision(
        decision_id="decision-validated-v1",
        subject_id="consolidation-breakout-candidate-v1",
        state=ResearchDecisionState.VALIDATED,
        experiment_ids=("exp-confirmatory-001",),
        evidence_references=("validation-report-v1",),
        rationale="Comparator-adjusted evidence survived the frozen validation design.",
        decided_by="research-reviewer",
        decided_at="2026-08-14T00:20:00+00:00",
    )


def _profile():
    return canonical_research_reporting_profile(
        required_roles=(
            EvidenceRole.VALIDATION,
            EvidenceRole.WALK_FORWARD,
            EvidenceRole.ROBUSTNESS,
            EvidenceRole.FINAL_HOLDOUT,
        )
    )


def test_package_preserves_provenance_samples_paths_and_decision() -> None:
    package = build_research_evidence_package(
        manifest=_manifest(),
        review=_review(),
        primary_evidence_id="validation-primary",
        profile=_profile(),
        decision=_decision(),
    )
    summary = summarize_research_evidence_package(package)

    assert package.experiment_id == "exp-confirmatory-001"
    assert package.dataset_version == "canonical-us-equity-v17"
    assert package.primary_sample.raw_event_count == 120
    assert package.primary_sample.effective_sample_size == 63.5
    assert package.primary_metric("win_probability").interval is not None
    assert len(package.primary_effects) == 1
    assert len(package.walk_forward_snapshots) == 1
    assert len(package.robustness_snapshots) == 1
    assert len(package.final_holdout_snapshots) == 1
    assert package.decision_state is ResearchDecisionState.VALIDATED
    assert summary.walk_forward_fold_count == 1
    assert summary.robustness_challenge_count == 1
    assert summary.multiplicity_family_count == 1


def test_package_checksum_is_deterministic_and_changes_with_evidence() -> None:
    first = build_research_evidence_package(
        manifest=_manifest(),
        review=_review(),
        primary_evidence_id="validation-primary",
        profile=_profile(),
    )
    second = build_research_evidence_package(
        manifest=_manifest(),
        review=_review(),
        primary_evidence_id="validation-primary",
        profile=_profile(),
    )
    assert first.package_checksum == second.package_checksum
    assert first.package_id == second.package_id

    changed_metrics = tuple(
        replace(metric, estimate=0.05) if metric.metric == "mean_outcome" else metric
        for metric in _primary_metrics()
    )
    changed = build_research_evidence_package(
        manifest=_manifest(),
        review=_review(primary_metrics=changed_metrics),
        primary_evidence_id="validation-primary",
        profile=_profile(),
    )
    assert changed.package_checksum != first.package_checksum


def test_missing_standard_metric_fails_closed() -> None:
    incomplete = tuple(metric for metric in _primary_metrics() if metric.metric != "expectancy")
    with pytest.raises(ValueError, match="missing required reporting metrics"):
        build_research_evidence_package(
            manifest=_manifest(),
            review=_review(primary_metrics=incomplete),
            primary_evidence_id="validation-primary",
            profile=_profile(),
        )


def test_missing_required_role_fails_closed() -> None:
    profile = canonical_research_reporting_profile(
        required_roles=(EvidenceRole.DEVELOPMENT, EvidenceRole.VALIDATION)
    )
    with pytest.raises(ValueError, match="missing required evidence roles: DEVELOPMENT"):
        build_research_evidence_package(
            manifest=_manifest(),
            review=_review(),
            primary_evidence_id="validation-primary",
            profile=profile,
        )


def test_package_rejects_cross_experiment_decision() -> None:
    decision = replace(_decision(), experiment_ids=("another-experiment",))
    with pytest.raises(ValueError, match="does not cite the packaged experiment"):
        build_research_evidence_package(
            manifest=_manifest(),
            review=_review(),
            primary_evidence_id="validation-primary",
            profile=_profile(),
            decision=decision,
        )


def test_package_rejects_validation_report_from_another_experiment() -> None:
    review = _review()
    bad_report = replace(review.report, experiment_id="another-experiment")
    bad_review = replace(review, report=bad_report)
    with pytest.raises(ValueError, match="different experiments"):
        build_research_evidence_package(
            manifest=_manifest(),
            review=bad_review,
            primary_evidence_id="validation-primary",
            profile=_profile(),
        )
