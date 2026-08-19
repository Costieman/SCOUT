"""Evidence comparison and governed promotion for strategy-suite research.

Phase 9 compares strategy families without collapsing heterogeneous evidence into one winner score.
Phase 10 recommends lifecycle promotion only when explicit validation, robustness, cost, holdout,
and operational gates are satisfied. This module never mutates validation evidence or scanner state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.app.strategy_suite_registry import SuiteImplementationStatus, strategy_suite


class StrategyLifecycle(StrEnum):
    IDEA = "idea"
    EXPLORATORY = "exploratory"
    CANDIDATE = "candidate"
    VALIDATION = "validation"
    VALIDATED = "validated"
    PRODUCTION_ELIGIBLE = "production_eligible"
    SCANNER = "scanner"


@dataclass(frozen=True, slots=True)
class SuiteEvidenceSnapshot:
    """Comparable evidence summary for one fixed suite/configuration version."""

    suite_id: str
    configuration_fingerprint: str
    expectancy_pct: float
    max_drawdown_pct: float
    effective_sample_size: float
    validation_stability: float
    cost_adjusted_expectancy_pct: float
    holdout_passed: bool = False
    robustness_passed: bool = False

    def __post_init__(self) -> None:
        strategy_suite(self.suite_id)
        if not self.configuration_fingerprint.strip():
            raise ValueError("configuration_fingerprint must be non-empty")
        if self.max_drawdown_pct < 0:
            raise ValueError("max_drawdown_pct must be non-negative")
        if self.effective_sample_size < 0:
            raise ValueError("effective_sample_size must be non-negative")
        if not 0 <= self.validation_stability <= 1:
            raise ValueError("validation_stability must be between 0 and 1")

    @property
    def family(self) -> str:
        return strategy_suite(self.suite_id).family


@dataclass(frozen=True, slots=True)
class FamilyComparison:
    """Pairwise evidence comparison that preserves trade-offs rather than inventing one score."""

    left: SuiteEvidenceSnapshot
    right: SuiteEvidenceSnapshot
    dominant_suite_id: str | None
    tradeoffs: tuple[str, ...]


def compare_suite_evidence(
    left: SuiteEvidenceSnapshot,
    right: SuiteEvidenceSnapshot,
) -> FamilyComparison:
    """Compare two fixed configurations using transparent Pareto-style dominance."""

    if left.configuration_fingerprint == right.configuration_fingerprint:
        raise ValueError("cannot compare the same resolved configuration with itself")

    left_metrics = (
        left.cost_adjusted_expectancy_pct,
        -left.max_drawdown_pct,
        left.effective_sample_size,
        left.validation_stability,
    )
    right_metrics = (
        right.cost_adjusted_expectancy_pct,
        -right.max_drawdown_pct,
        right.effective_sample_size,
        right.validation_stability,
    )
    left_no_worse = all(a >= b for a, b in zip(left_metrics, right_metrics, strict=True))
    right_no_worse = all(b >= a for a, b in zip(left_metrics, right_metrics, strict=True))
    left_better = any(a > b for a, b in zip(left_metrics, right_metrics, strict=True))
    right_better = any(b > a for a, b in zip(left_metrics, right_metrics, strict=True))

    dominant: str | None = None
    if left_no_worse and left_better:
        dominant = left.suite_id
    elif right_no_worse and right_better:
        dominant = right.suite_id

    tradeoffs: list[str] = []
    labels = (
        "cost-adjusted expectancy",
        "drawdown control",
        "effective sample size",
        "validation stability",
    )
    for label, a, b in zip(labels, left_metrics, right_metrics, strict=True):
        if a > b:
            tradeoffs.append(f"{left.suite_id} stronger on {label}")
        elif b > a:
            tradeoffs.append(f"{right.suite_id} stronger on {label}")
        else:
            tradeoffs.append(f"equal on {label}")

    return FamilyComparison(
        left=left,
        right=right,
        dominant_suite_id=dominant,
        tradeoffs=tuple(tradeoffs),
    )


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    """Explicit gates used to recommend one next lifecycle state."""

    snapshot: SuiteEvidenceSnapshot
    current_state: StrategyLifecycle
    validation_plan_frozen: bool = False
    comparator_included: bool = False
    costs_included: bool = False
    replay_parity_passed: bool = False
    data_quality_gate_passed: bool = False
    freshness_gate_passed: bool = False
    minimum_effective_sample_size: float = 30.0


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    current_state: StrategyLifecycle
    recommended_state: StrategyLifecycle
    eligible: bool
    blockers: tuple[str, ...]
    rationale: str


def evaluate_promotion(evidence: PromotionEvidence) -> PromotionDecision:
    """Recommend at most the next lifecycle state; never auto-promote or skip governance stages."""

    snapshot = evidence.snapshot
    suite = strategy_suite(snapshot.suite_id)
    blockers: list[str] = []

    if suite.implementation_status is not SuiteImplementationStatus.READY:
        blockers.append("suite is not fully executable")
    if snapshot.effective_sample_size < evidence.minimum_effective_sample_size:
        blockers.append("effective sample size is below the declared minimum")

    next_state = _next_state(evidence.current_state)

    if next_state in {
        StrategyLifecycle.CANDIDATE,
        StrategyLifecycle.VALIDATION,
        StrategyLifecycle.VALIDATED,
        StrategyLifecycle.PRODUCTION_ELIGIBLE,
        StrategyLifecycle.SCANNER,
    }:
        if snapshot.cost_adjusted_expectancy_pct <= 0:
            blockers.append("cost-adjusted expectancy is not positive")
        if not evidence.comparator_included:
            blockers.append("required comparator evidence is missing")

    if (
        next_state
        in {
            StrategyLifecycle.VALIDATION,
            StrategyLifecycle.VALIDATED,
            StrategyLifecycle.PRODUCTION_ELIGIBLE,
            StrategyLifecycle.SCANNER,
        }
        and not evidence.validation_plan_frozen
    ):
        blockers.append("validation plan is not frozen")

    if next_state in {
        StrategyLifecycle.VALIDATED,
        StrategyLifecycle.PRODUCTION_ELIGIBLE,
        StrategyLifecycle.SCANNER,
    }:
        if not snapshot.holdout_passed:
            blockers.append("final holdout has not passed")
        if not snapshot.robustness_passed:
            blockers.append("robustness checks have not passed")
        if not evidence.costs_included:
            blockers.append("transaction costs are not included")

    if next_state in {StrategyLifecycle.PRODUCTION_ELIGIBLE, StrategyLifecycle.SCANNER}:
        if snapshot.validation_stability < 0.60:
            blockers.append("validation stability is below the production threshold")

    if next_state is StrategyLifecycle.SCANNER:
        if not evidence.replay_parity_passed:
            blockers.append("historical replay parity has not passed")
        if not evidence.data_quality_gate_passed:
            blockers.append("data-quality gate has not passed")
        if not evidence.freshness_gate_passed:
            blockers.append("freshness gate has not passed")

    eligible = not blockers
    recommended = next_state if eligible else evidence.current_state
    rationale = (
        f"Advance only one stage to {next_state.value}; all explicit gates passed."
        if eligible
        else "Remain at the current stage until the listed evidence gaps are resolved."
    )
    return PromotionDecision(
        current_state=evidence.current_state,
        recommended_state=recommended,
        eligible=eligible,
        blockers=tuple(blockers),
        rationale=rationale,
    )


def _next_state(state: StrategyLifecycle) -> StrategyLifecycle:
    order = (
        StrategyLifecycle.IDEA,
        StrategyLifecycle.EXPLORATORY,
        StrategyLifecycle.CANDIDATE,
        StrategyLifecycle.VALIDATION,
        StrategyLifecycle.VALIDATED,
        StrategyLifecycle.PRODUCTION_ELIGIBLE,
        StrategyLifecycle.SCANNER,
    )
    index = order.index(state)
    return order[min(index + 1, len(order) - 1)]


__all__ = [
    "FamilyComparison",
    "PromotionDecision",
    "PromotionEvidence",
    "StrategyLifecycle",
    "SuiteEvidenceSnapshot",
    "compare_suite_evidence",
    "evaluate_promotion",
]
