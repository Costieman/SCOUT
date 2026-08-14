"""Reproducible risk-policy comparison harness over one frozen event population."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from trade_scout.data.contracts import ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.risk.initial_stops import (
    CostModel,
    PrematureStopDefinition,
    RiskPolicyResult,
    StopFamily,
    StopPolicy,
    StructuralStopContext,
    evaluate_stop_policy_grid,
    initial_stop_policy_grid,
)
from trade_scout.statistics.stop_research import (
    StopResearchComparison,
    summarize_stop_policy_results,
)

HYBRID_BASELINE_ATR_MULTIPLE = 2.0


@dataclass(frozen=True, slots=True)
class RiskPolicyComparisonRun:
    """One policy-grid execution with explicit common-population accounting."""

    requested_event_ids: tuple[str, ...]
    evaluated_event_ids: tuple[str, ...]
    excluded_event_ids: tuple[str, ...]
    policies: tuple[StopPolicy, ...]
    event_results: tuple[RiskPolicyResult, ...]
    comparison: StopResearchComparison
    harness_definition_version: str = "risk-policy-comparison-harness-v0.1"


def comparison_stop_policy_grid() -> tuple[StopPolicy, ...]:
    """Return the baseline simple-stop grid plus one explicit structural/ATR hybrid.

    The hybrid is an infrastructure baseline, not a scientific recommendation. Its stop is the
    wider (lower, for a long position) of consolidation support and entry minus 2x pre-entry ATR.
    """

    hybrid = StopPolicy(
        policy_id="hybrid-base-low-or-2atr-wider",
        family=StopFamily.HYBRID_STRUCTURAL_ATR,
        parameters=MappingProxyType({"atr_multiple": HYBRID_BASELINE_ATR_MULTIPLE}),
    )
    return (*initial_stop_policy_grid(), hybrid)


def run_risk_policy_comparison(
    bars: tuple[ResearchBar, ...],
    events: tuple[EventRecord, ...],
    *,
    horizon: int,
    policies: tuple[StopPolicy, ...] | None = None,
    cost_model: CostModel = CostModel(),
    structural_contexts: Mapping[str, StructuralStopContext] | None = None,
    premature_success: PrematureStopDefinition = PrematureStopDefinition(),
) -> RiskPolicyComparisonRun:
    """Apply all policies to one exact eligible event set and assemble descriptive evidence."""

    resolved_policies = policies or comparison_stop_policy_grid()
    requested_event_ids = tuple(event.event_id for event in events)
    if len(set(requested_event_ids)) != len(requested_event_ids):
        raise ValueError("risk comparison input contains duplicate event IDs")

    results = evaluate_stop_policy_grid(
        bars,
        events,
        horizon=horizon,
        policies=resolved_policies,
        cost_model=cost_model,
        structural_contexts=structural_contexts,
        premature_success=premature_success,
    )
    no_stop_id = next(
        policy.policy_id for policy in resolved_policies if policy.family is StopFamily.NO_STOP
    )
    evaluated_event_ids = tuple(
        result.event_id for result in results if result.risk_policy_id == no_stop_id
    )
    evaluated_set = set(evaluated_event_ids)
    excluded_event_ids = tuple(
        event_id for event_id in requested_event_ids if event_id not in evaluated_set
    )

    comparison = summarize_stop_policy_results(
        results,
        policies=resolved_policies,
        horizon=horizon,
        entry_slippage_bps=cost_model.entry_slippage_bps,
        exit_slippage_bps=cost_model.exit_slippage_bps,
        stop_slippage_bps=cost_model.stop_slippage_bps,
        commission_bps_per_side=cost_model.commission_bps_per_side,
    )
    return RiskPolicyComparisonRun(
        requested_event_ids=requested_event_ids,
        evaluated_event_ids=evaluated_event_ids,
        excluded_event_ids=excluded_event_ids,
        policies=resolved_policies,
        event_results=results,
        comparison=comparison,
    )


__all__ = [
    "HYBRID_BASELINE_ATR_MULTIPLE",
    "RiskPolicyComparisonRun",
    "comparison_stop_policy_grid",
    "run_risk_policy_comparison",
]
