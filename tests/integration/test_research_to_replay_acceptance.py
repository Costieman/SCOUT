"""End-to-end acceptance for the governed research-to-replay provenance chain."""

from __future__ import annotations

from types import MappingProxyType

from trade_scout.events import replay_consolidation_pipeline
from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
    StageRecord,
)
from trade_scout.experiments.decisions import (
    ProductionEligibilityAttestation,
    ResearchDecision,
    ResearchDecisionState,
)
from trade_scout.outcomes import OutcomePathStatus, measure_outcome_paths
from trade_scout.patterns import PatternLifecycleState
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.risk import (
    StopFamily,
    StopPolicy,
    structural_stop_context_from_pattern_state,
)
from trade_scout.scanner import (
    ConsolidationReplayEvaluator,
    ReplayPublicationClass,
    ScanCandidateState,
    run_historical_replay,
    strategy_from_research_evidence,
)
from trade_scout.statistics import run_risk_policy_comparison
from trade_scout.synthetic import SyntheticAnnotationKind, consolidation_breakout_scenario
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
from trade_scout.validation.research_package import (
    build_research_evidence_package,
    canonical_research_reporting_profile,
)

_STRATEGY_VERSION = "synthetic-consolidation-strategy-v1"
_RISK_POLICY_ID = "fixed-5pct-acceptance"


def _config() -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=10,
        max_range_pct=0.04,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
    )


def _risk_policies() -> tuple[StopPolicy, ...]:
    return (
        StopPolicy(
            policy_id="no-stop-acceptance",
            family=StopFamily.NO_STOP,
            parameters=MappingProxyType({}),
        ),
        StopPolicy(
            policy_id=_RISK_POLICY_ID,
            family=StopFamily.FIXED_PERCENT,
            parameters=MappingProxyType({"distance_pct": 0.05}),
        ),
    )


def test_research_event_evidence_and_replay_preserve_one_traceable_definition() -> None:
    scenario = consolidation_breakout_scenario()
    breakout = next(
        annotation
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.BREAKOUT
    )
    as_of_date = breakout.start_date
    research_bars = tuple(bar for bar in scenario.raw_bars if bar.trade_date <= as_of_date)
    replay = replay_consolidation_pipeline(research_bars, _config())

    assert len(replay.events) == 1
    event = replay.events[0]
    consumed = next(
        state
        for state in replay.pattern_states
        if state.state is PatternLifecycleState.CONSUMED
        and state.pattern_instance_id == event.pattern_instance_id
    )

    outcome = measure_outcome_paths(scenario.raw_bars, (event,), horizons=(5,))[0]
    assert outcome.status is OutcomePathStatus.COMPLETE
    assert outcome.forward_return is not None
    assert outcome.mae is not None
    assert outcome.mfe is not None

    structural_context = structural_stop_context_from_pattern_state(event, consumed)
    risk_run = run_risk_policy_comparison(
        scenario.raw_bars,
        (event,),
        horizon=5,
        policies=_risk_policies(),
        structural_contexts={event.event_id: structural_context},
    )
    assert risk_run.evaluated_event_ids == (event.event_id,)
    assert {summary.sample_size for summary in risk_run.comparison.policy_summaries} == {1}

    package = build_research_evidence_package(
        manifest=_manifest(str(scenario.raw_bars[0].dataset_version)),
        review=_review(outcome.forward_return, outcome.mae, outcome.mfe),
        primary_evidence_id="acceptance-validation",
        profile=canonical_research_reporting_profile(required_roles=(EvidenceRole.VALIDATION,)),
        decision=_production_decision(),
    )
    evaluator = ConsolidationReplayEvaluator(_config())
    strategy = strategy_from_research_evidence(
        package,
        strategy_family_id="consolidation-breakout",
        strategy_version=_STRATEGY_VERSION,
        feature_set_version=evaluator.feature_set_version,
        risk_policy_id=_RISK_POLICY_ID,
    )
    instrument_id = research_bars[-1].instrument_id
    scan = run_historical_replay(
        strategy=strategy,
        as_of_date=as_of_date,
        universe_version=package.universe_version,
        eligible_instrument_ids=(instrument_id,),
        bars_by_instrument={instrument_id: scenario.raw_bars},
        ticker_display_by_instrument={instrument_id: "SYN"},
        evaluator=evaluator,
    )

    assert scan.replay_publication_class is ReplayPublicationClass.PRODUCTION_COMPATIBLE
    assert scan.dataset_version == package.dataset_version
    assert scan.evidence_package_checksum == package.package_checksum
    assert scan.risk_policy_id == _RISK_POLICY_ID
    assert len(scan.candidates) == 1
    candidate = scan.candidates[0]
    assert candidate.candidate_state is ScanCandidateState.TRIGGERED
    assert candidate.event_id == event.event_id
    assert candidate.pattern_instance_id == event.pattern_instance_id
    assert candidate.evidence_profile_id == package.package_id
    assert candidate.dataset_version == package.dataset_version
    assert candidate.rank_score is None
    assert candidate.rank_model_version is None


def _manifest(dataset_version: str) -> ExperimentManifest:
    definition = ExperimentDefinition(
        name="Synthetic research-to-replay acceptance",
        hypothesis="A frozen synthetic definition preserves identity through replay.",
        mode=ResearchMode.CONFIRMATORY,
        dataset_version=dataset_version,
        universe_version="synthetic-point-in-time-universe-v1",
        code_version="acceptance-sweep-code-v1",
        config_schema_version="experiment-config-v0.1",
        resolved_configuration={
            "pattern_duration": 10,
            "max_range_pct": 0.04,
            "outcome_horizon": 5,
            "risk_policy_id": _RISK_POLICY_ID,
        },
        hypothesis_family_id="research-to-replay-acceptance-v1",
    )
    return ExperimentManifest(
        experiment_id="research-to-replay-acceptance-exp-v1",
        definition=definition,
        status=ExperimentStatus.SUCCEEDED,
        created_at="2026-08-15T00:00:00+00:00",
        started_at="2026-08-15T00:01:00+00:00",
        completed_at="2026-08-15T00:02:00+00:00",
        stages=(
            StageRecord(
                stage_name="synthetic-validation",
                started_at="2026-08-15T00:01:00+00:00",
                completed_at="2026-08-15T00:02:00+00:00",
                output_checksum="synthetic-validation-output-v1",
                warnings=(),
            ),
        ),
        manifest_checksum="synthetic-acceptance-manifest-v1",
    )


def _review(
    forward_return: float,
    mae: float,
    mfe: float,
) -> ValidationReviewBundle:
    win_probability = 1.0 if forward_return > 0 else 0.0
    interval = ConfidenceInterval(
        lower=win_probability,
        upper=win_probability,
        confidence_level=0.95,
        method="synthetic-contract-fixture",
    )
    metrics = (
        MetricEstimate("mean_outcome", forward_return, "return_fraction"),
        MetricEstimate("median_outcome", forward_return, "return_fraction"),
        MetricEstimate("win_probability", win_probability, "probability", interval=interval),
        MetricEstimate("expectancy", forward_return, "return_fraction"),
        MetricEstimate("return_quantile_p05", forward_return, "return_fraction"),
        MetricEstimate("return_quantile_p50", forward_return, "return_fraction"),
        MetricEstimate("return_quantile_p95", forward_return, "return_fraction"),
        MetricEstimate("mae_quantile_p10", mae, "return_fraction"),
        MetricEstimate("mae_quantile_p50", mae, "return_fraction"),
        MetricEstimate("mae_quantile_p90", mae, "return_fraction"),
        MetricEstimate("mfe_quantile_p10", mfe, "return_fraction"),
        MetricEstimate("mfe_quantile_p50", mfe, "return_fraction"),
        MetricEstimate("mfe_quantile_p90", mfe, "return_fraction"),
    )
    sample = SampleAccounting(
        raw_event_count=1,
        unique_instrument_count=1,
        effective_sample_size=1.0,
        cluster_count=1,
    )
    comparator = ComparatorDefinition(
        comparator_id="synthetic-contract-baseline",
        kind=ComparatorKind.SIMPLE_EVENT_BASELINE,
        description="Synthetic contract comparator used only for architecture acceptance.",
    )
    effect = EffectEstimate(
        effect_id="synthetic-contract-effect",
        metric="forward_return",
        estimate=0.0,
        units="return_fraction",
        comparator=comparator,
        sample=sample,
        interval=ConfidenceInterval(
            lower=0.0,
            upper=0.0,
            confidence_level=0.95,
            method="synthetic-contract-fixture",
        ),
    )
    snapshot = EvidenceSnapshot(
        evidence_id="acceptance-validation",
        role=EvidenceRole.VALIDATION,
        sample=sample,
        metrics=metrics,
        effects=(effect,),
    )
    report = ValidationEvidenceReport(
        report_id="acceptance-validation-report-v1",
        experiment_id="research-to-replay-acceptance-exp-v1",
        validation_plan_id="acceptance-validation-plan-v1",
        primary_outcome="forward_return_5_sessions",
        snapshots=(snapshot,),
        notes=("Synthetic acceptance evidence is not a scientific promotion claim.",),
    )
    counts = tuple(
        ValidationRoleCount(role, 1 if role is EvidenceRole.VALIDATION else 0)
        for role in EvidenceRole
    )
    return ValidationReviewBundle(
        report=report,
        assignments=(),
        completeness=ValidationCompleteness(True, (), (), (), ()),
        role_counts=counts,
    )


def _production_decision() -> ResearchDecision:
    return ResearchDecision(
        decision_id="synthetic-acceptance-production-decision-v1",
        subject_id=_STRATEGY_VERSION,
        state=ResearchDecisionState.PRODUCTION_ELIGIBLE,
        experiment_ids=("research-to-replay-acceptance-exp-v1",),
        evidence_references=("acceptance-validation-report-v1",),
        rationale="Synthetic fixture exists only to exercise the production eligibility gate.",
        decided_by="architecture-acceptance-test",
        decided_at="2026-08-15T00:03:00+00:00",
        production_attestation=ProductionEligibilityAttestation(
            implementation_compatible=True,
            cost_assumptions_acceptable=True,
            liquidity_assumptions_acceptable=True,
            risk_policy_validated=True,
            operational_dependencies_available=True,
        ),
    )
