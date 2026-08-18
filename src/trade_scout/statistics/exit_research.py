"""Descriptive comparison for generic post-entry exit policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from statistics import median

from trade_scout.risk.exit_policies import (
    ExitFamily,
    ExitPolicy,
    ExitPolicyResult,
    TargetFamily,
)


@dataclass(frozen=True, slots=True)
class ExitPolicySummary:
    """Market-wide descriptive evidence for one resolved exit policy."""

    policy_id: str
    policy_version: str
    family: ExitFamily
    resolved_parameters: Mapping[str, float]
    target_family: TargetFamily | None
    target_parameters: Mapping[str, float]
    sample_size: int
    stop_out_count: int
    stop_out_rate: float
    target_hit_count: int
    target_hit_rate: float
    same_bar_ambiguous_count: int
    same_bar_ambiguous_rate: float
    expectancy: float | None
    expectancy_delta_vs_hold: float | None
    median_return: float | None
    win_probability: float | None
    average_winner: float | None
    average_loser: float | None
    payoff_ratio: float | None
    profit_factor: float | None
    tail_loss_p05: float | None
    average_holding_period_sessions: float | None
    median_holding_period_sessions: float | None
    median_mae_before_exit: float | None
    median_mfe_full_horizon: float | None
    median_max_drawdown_before_exit: float | None
    gap_through_frequency: float | None
    mean_gap_loss_pct: float | None
    mean_cost_drag_return: float | None


@dataclass(frozen=True, slots=True)
class ExitResearchComparison:
    """One exact-population comparison across configurable exit families."""

    horizon: int
    complete_event_count: int
    event_population_fingerprint: str
    policy_summaries: tuple[ExitPolicySummary, ...]
    warnings: tuple[str, ...]
    research_state: str = "EXPLORATORY"
    comparison_definition_version: str = "generic-exit-comparison-v0.2"


def summarize_exit_policy_results(
    results: tuple[ExitPolicyResult, ...],
    *,
    policies: tuple[ExitPolicy, ...],
    horizon: int,
) -> ExitResearchComparison:
    """Aggregate results while enforcing an identical event population for every policy."""

    if horizon < 1:
        raise ValueError("exit comparison horizon must be positive")
    if not policies:
        raise ValueError("exit comparison requires at least one policy")
    if len({item.policy_id for item in policies}) != len(policies):
        raise ValueError("exit policy IDs must be unique")

    by_policy: dict[str, list[ExitPolicyResult]] = {item.policy_id: [] for item in policies}
    for result in results:
        if result.policy_id not in by_policy:
            raise ValueError(f"result references unknown exit policy {result.policy_id}")
        by_policy[result.policy_id].append(result)

    hold_policy = next(
        (
            item
            for item in policies
            if item.family is ExitFamily.HOLD_TO_HORIZON and item.target_family is None
        ),
        None,
    )
    if hold_policy is None:
        raise ValueError("exit comparison requires a pure hold-to-horizon baseline")
    hold_results = tuple(by_policy[hold_policy.policy_id])
    baseline_ids = tuple(item.event_id for item in hold_results)
    if len(set(baseline_ids)) != len(baseline_ids):
        raise ValueError("hold baseline contains duplicate event results")
    baseline_population = set(baseline_ids)

    for policy in policies:
        policy_results = tuple(by_policy[policy.policy_id])
        event_ids = tuple(item.event_id for item in policy_results)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError(f"policy {policy.policy_id} contains duplicate event results")
        if set(event_ids) != baseline_population:
            raise ValueError("exit policies must be compared on the exact same event population")

    hold_mean = _mean(tuple(item.realized_return for item in hold_results))
    summaries = tuple(
        _summary(
            policy,
            tuple(by_policy[policy.policy_id]),
            hold_mean=hold_mean,
        )
        for policy in policies
    )
    target_enabled = any(item.target_family is not None for item in policies)
    warnings = [
        "Exit policies are applied after event detection and never change which events existed.",
        (
            "The maximum holding period is a research backstop and scientific control. Managed "
            "plans may exit earlier when their protective stop or profit target triggers."
        ),
        (
            "Trailing stops use only the prior session's completed high-water mark; same-session "
            "high/low ordering is never invented from daily OHLC bars."
        ),
        (
            "Every policy is required to use the exact same complete event IDs, not merely the "
            "same sample size."
        ),
        (
            "This grid is exploratory. The best-looking row is not a validated recommendation "
            "without multiplicity control and out-of-sample testing."
        ),
    ]
    if target_enabled:
        warnings.insert(
            3,
            (
                "When one daily bar touches both a stop and target, the configured same-bar "
                "ordering assumption is recorded and the ambiguous case is counted explicitly."
            ),
        )
    fingerprint = sha256("\n".join(sorted(baseline_population)).encode()).hexdigest()
    return ExitResearchComparison(
        horizon=horizon,
        complete_event_count=len(hold_results),
        event_population_fingerprint=fingerprint,
        policy_summaries=summaries,
        warnings=tuple(warnings),
    )


def _summary(
    policy: ExitPolicy,
    results: tuple[ExitPolicyResult, ...],
    *,
    hold_mean: float | None,
) -> ExitPolicySummary:
    returns = tuple(item.realized_return for item in results)
    winners = tuple(value for value in returns if value > 0)
    losers = tuple(value for value in returns if value < 0)
    stopped = tuple(item for item in results if item.stopped)
    targeted = tuple(item for item in results if item.targeted)
    ambiguous = tuple(item for item in results if item.same_bar_stop_target_ambiguous)
    gaps = tuple(item for item in stopped if item.gap_through_stop)
    expectancy = _mean(returns)
    average_winner = _mean(winners)
    average_loser = _mean(losers)
    payoff_ratio = (
        average_winner / abs(average_loser)
        if average_winner is not None and average_loser is not None and average_loser != 0
        else None
    )
    return ExitPolicySummary(
        policy_id=policy.policy_id,
        policy_version=policy.version,
        family=policy.family,
        resolved_parameters=policy.parameters,
        target_family=policy.target_family,
        target_parameters=policy.target_parameters,
        sample_size=len(results),
        stop_out_count=len(stopped),
        stop_out_rate=len(stopped) / len(results) if results else 0.0,
        target_hit_count=len(targeted),
        target_hit_rate=len(targeted) / len(results) if results else 0.0,
        same_bar_ambiguous_count=len(ambiguous),
        same_bar_ambiguous_rate=len(ambiguous) / len(results) if results else 0.0,
        expectancy=expectancy,
        expectancy_delta_vs_hold=(
            expectancy - hold_mean if expectancy is not None and hold_mean is not None else None
        ),
        median_return=median(returns) if returns else None,
        win_probability=sum(value > 0 for value in returns) / len(returns) if returns else None,
        average_winner=average_winner,
        average_loser=average_loser,
        payoff_ratio=payoff_ratio,
        profit_factor=_profit_factor(winners, losers),
        tail_loss_p05=_quantile(tuple(sorted(returns)), 0.05) if returns else None,
        average_holding_period_sessions=_mean(
            tuple(float(item.holding_period_sessions) for item in results)
        ),
        median_holding_period_sessions=(
            median(item.holding_period_sessions for item in results) if results else None
        ),
        median_mae_before_exit=(
            median(item.mae_before_exit for item in results) if results else None
        ),
        median_mfe_full_horizon=(
            median(item.mfe_full_horizon for item in results) if results else None
        ),
        median_max_drawdown_before_exit=(
            median(item.max_drawdown_before_exit for item in results) if results else None
        ),
        gap_through_frequency=len(gaps) / len(stopped) if stopped else None,
        mean_gap_loss_pct=_mean(tuple(item.gap_loss_pct for item in gaps)),
        mean_cost_drag_return=_mean(tuple(item.cost_drag_return for item in results)),
    )


def _mean(values: tuple[float, ...]) -> float | None:
    return sum(values) / len(values) if values else None


def _profit_factor(winners: tuple[float, ...], losers: tuple[float, ...]) -> float | None:
    gross_loss = abs(sum(losers))
    if gross_loss == 0:
        return None
    return sum(winners) / gross_loss


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    if len(values) == 1:
        return values[0]
    position = probability * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


__all__ = [
    "ExitPolicySummary",
    "ExitResearchComparison",
    "summarize_exit_policy_results",
]
