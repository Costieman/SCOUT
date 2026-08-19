from __future__ import annotations

import pytest

from trade_scout.app.strategy_suite_evidence import (
    PromotionEvidence,
    StrategyLifecycle,
    SuiteEvidenceSnapshot,
    compare_suite_evidence,
    evaluate_promotion,
)


def _snapshot(
    suite_id: str = "TS-S01-CONSOLIDATION-BREAKOUT",
    *,
    fingerprint: str = "cfg-a",
    expectancy: float = 1.2,
    drawdown: float = 8.0,
    sample: float = 120.0,
    stability: float = 0.75,
    cost_expectancy: float = 0.8,
    holdout: bool = True,
    robustness: bool = True,
) -> SuiteEvidenceSnapshot:
    return SuiteEvidenceSnapshot(
        suite_id=suite_id,
        configuration_fingerprint=fingerprint,
        expectancy_pct=expectancy,
        max_drawdown_pct=drawdown,
        effective_sample_size=sample,
        validation_stability=stability,
        cost_adjusted_expectancy_pct=cost_expectancy,
        holdout_passed=holdout,
        robustness_passed=robustness,
    )


def test_phase9_reports_tradeoffs_instead_of_forcing_one_winner() -> None:
    left = _snapshot(expectancy=1.4, cost_expectancy=1.0, drawdown=12.0, fingerprint="left")
    right = _snapshot(
        suite_id="TS-S14-TIME-SERIES-MOMENTUM",
        expectancy=1.0,
        cost_expectancy=0.7,
        drawdown=6.0,
        sample=180.0,
        fingerprint="right",
    )
    result = compare_suite_evidence(left, right)
    assert result.dominant_suite_id is None
    assert any("cost-adjusted expectancy" in item for item in result.tradeoffs)
    assert any("drawdown control" in item for item in result.tradeoffs)


def test_phase9_identifies_pareto_dominance_only_when_no_metric_is_worse() -> None:
    strong = _snapshot(fingerprint="strong", cost_expectancy=1.2, drawdown=5.0, sample=180, stability=0.9)
    weak = _snapshot(
        suite_id="TS-S15-MA-CROSSOVER",
        fingerprint="weak",
        cost_expectancy=0.3,
        drawdown=9.0,
        sample=80,
        stability=0.6,
    )
    assert compare_suite_evidence(strong, weak).dominant_suite_id == strong.suite_id


def test_phase9_rejects_self_comparison() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="same resolved configuration"):
        compare_suite_evidence(snapshot, snapshot)


def test_phase10_advances_only_one_stage_when_gates_pass() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(),
        current_state=StrategyLifecycle.EXPLORATORY,
        comparator_included=True,
    )
    decision = evaluate_promotion(evidence)
    assert decision.eligible is True
    assert decision.recommended_state is StrategyLifecycle.CANDIDATE


def test_phase10_blocks_candidate_when_cost_adjusted_edge_is_not_positive() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(cost_expectancy=0.0),
        current_state=StrategyLifecycle.EXPLORATORY,
        comparator_included=True,
    )
    decision = evaluate_promotion(evidence)
    assert decision.eligible is False
    assert "cost-adjusted expectancy is not positive" in decision.blockers


def test_phase10_requires_frozen_plan_before_validation() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(),
        current_state=StrategyLifecycle.CANDIDATE,
        comparator_included=True,
        validation_plan_frozen=False,
    )
    decision = evaluate_promotion(evidence)
    assert decision.recommended_state is StrategyLifecycle.CANDIDATE
    assert "validation plan is not frozen" in decision.blockers


def test_phase10_requires_holdout_robustness_and_costs_for_validated_state() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(holdout=False, robustness=False),
        current_state=StrategyLifecycle.VALIDATION,
        comparator_included=True,
        validation_plan_frozen=True,
        costs_included=False,
    )
    decision = evaluate_promotion(evidence)
    assert decision.eligible is False
    assert "final holdout has not passed" in decision.blockers
    assert "robustness checks have not passed" in decision.blockers
    assert "transaction costs are not included" in decision.blockers


def test_phase10_blocks_non_ready_structural_suite_from_promotion() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(suite_id="TS-S08-VCP"),
        current_state=StrategyLifecycle.EXPLORATORY,
        comparator_included=True,
    )
    decision = evaluate_promotion(evidence)
    assert "suite is not fully executable" in decision.blockers


def test_phase10_scanner_requires_operational_replay_and_data_gates() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(),
        current_state=StrategyLifecycle.PRODUCTION_ELIGIBLE,
        comparator_included=True,
        validation_plan_frozen=True,
        costs_included=True,
    )
    decision = evaluate_promotion(evidence)
    assert decision.eligible is False
    assert "historical replay parity has not passed" in decision.blockers
    assert "data-quality gate has not passed" in decision.blockers
    assert "freshness gate has not passed" in decision.blockers


def test_phase10_scanner_advances_only_after_all_operational_gates() -> None:
    evidence = PromotionEvidence(
        snapshot=_snapshot(),
        current_state=StrategyLifecycle.PRODUCTION_ELIGIBLE,
        comparator_included=True,
        validation_plan_frozen=True,
        costs_included=True,
        replay_parity_passed=True,
        data_quality_gate_passed=True,
        freshness_gate_passed=True,
    )
    decision = evaluate_promotion(evidence)
    assert decision.eligible is True
    assert decision.recommended_state is StrategyLifecycle.SCANNER
