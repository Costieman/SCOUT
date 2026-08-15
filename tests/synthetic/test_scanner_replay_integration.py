from __future__ import annotations

from trade_scout.events import replay_consolidation_pipeline
from trade_scout.experiments.decisions import (
    ProductionEligibilityAttestation,
    ResearchDecision,
    ResearchDecisionState,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.scanner import (
    ConsolidationReplayEvaluator,
    ScanCandidateState,
    ScanStrategyDefinition,
    run_historical_replay,
)
from trade_scout.synthetic import SyntheticAnnotationKind, consolidation_breakout_scenario


def _config() -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=10,
        max_range_pct=0.04,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
    )


def _strategy(evaluator: ConsolidationReplayEvaluator, dataset_version: str) -> ScanStrategyDefinition:
    decision = ResearchDecision(
        decision_id="scanner-replay-production-decision",
        subject_id="consolidation-breakout-strategy-v1",
        state=ResearchDecisionState.PRODUCTION_ELIGIBLE,
        experiment_ids=("scanner-replay-synthetic-experiment",),
        evidence_references=("scanner-replay-synthetic-evidence",),
        rationale="synthetic production-gate fixture",
        decided_by="test-suite",
        decided_at="2026-08-15T00:00:00Z",
        production_attestation=ProductionEligibilityAttestation(
            implementation_compatible=True,
            cost_assumptions_acceptable=True,
            liquidity_assumptions_acceptable=True,
            risk_policy_validated=True,
            operational_dependencies_available=True,
        ),
    )
    return ScanStrategyDefinition(
        strategy_family_id="consolidation-breakout",
        strategy_version="consolidation-breakout-strategy-v1",
        dataset_version=dataset_version,
        feature_set_version=evaluator.feature_set_version,
        evidence_profile_id="synthetic-evidence-profile-v1",
        evidence_package_checksum="synthetic-evidence-checksum-v1",
        code_version="synthetic-test-code-v1",
        config_schema_version="scanner-replay-config-v0.1",
        eligibility_decision=decision,
        risk_policy_id="no_stop",
    )


def test_historical_replay_matches_shared_event_engine_on_breakout_session() -> None:
    scenario = consolidation_breakout_scenario()
    breakout = next(
        item for item in scenario.annotations if item.kind is SyntheticAnnotationKind.BREAKOUT
    )
    as_of_date = breakout.start_date
    bars = tuple(bar for bar in scenario.raw_bars if bar.trade_date <= as_of_date)
    direct = replay_consolidation_pipeline(bars, _config())
    expected_event = direct.events[-1]
    evaluator = ConsolidationReplayEvaluator(_config())
    instrument = bars[-1].instrument_id

    result = run_historical_replay(
        strategy=_strategy(evaluator, str(bars[-1].dataset_version)),
        as_of_date=as_of_date,
        universe_version="synthetic-point-in-time-universe-v1",
        eligible_instrument_ids=(instrument,),
        bars_by_instrument={instrument: scenario.raw_bars},
        ticker_display_by_instrument={instrument: "SYN"},
        evaluator=evaluator,
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.candidate_state is ScanCandidateState.TRIGGERED
    assert candidate.event_id == expected_event.event_id
    assert candidate.pattern_instance_id == expected_event.pattern_instance_id
    assert {item.name for item in candidate.structural_levels} == {"resistance", "support"}


def test_replay_projection_is_invariant_to_future_suffix() -> None:
    scenario = consolidation_breakout_scenario()
    breakout = next(
        item for item in scenario.annotations if item.kind is SyntheticAnnotationKind.BREAKOUT
    )
    as_of_date = breakout.start_date
    prefix = tuple(bar for bar in scenario.raw_bars if bar.trade_date <= as_of_date)
    evaluator = ConsolidationReplayEvaluator(_config())
    instrument = prefix[-1].instrument_id
    strategy = _strategy(evaluator, str(prefix[-1].dataset_version))
    kwargs = {
        "strategy": strategy,
        "as_of_date": as_of_date,
        "universe_version": "synthetic-point-in-time-universe-v1",
        "eligible_instrument_ids": (instrument,),
        "ticker_display_by_instrument": {instrument: "SYN"},
        "evaluator": evaluator,
    }

    prefix_result = run_historical_replay(
        bars_by_instrument={instrument: prefix},
        **kwargs,
    )
    full_result = run_historical_replay(
        bars_by_instrument={instrument: scenario.raw_bars},
        **kwargs,
    )

    assert prefix_result.scan_run_id == full_result.scan_run_id
    assert prefix_result.output_checksum == full_result.output_checksum
    assert prefix_result.candidates == full_result.candidates
