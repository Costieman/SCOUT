"""Descriptive comparison of stop policies applied to the same historical event population."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from statistics import median

from trade_scout.risk.initial_stops import RiskPolicyResult, StopFamily, StopPolicy


@dataclass(frozen=True, slots=True)
class StopPolicySummary:
    """Market-wide descriptive evidence for one resolved stop policy."""

    policy_id: str
    policy_version: str
    stop_family: StopFamily
    resolved_parameters: Mapping[str, float]
    sample_size: int
    stop_out_count: int
    stop_out_rate: float
    expectancy: float | None
    expectancy_delta_vs_no_stop: float | None
    median_return: float | None
    win_probability: float | None
    average_winner: float | None
    median_winner: float | None
    average_loser: float | None
    median_loser: float | None
    profit_factor: float | None
    average_r: float | None
    median_r: float | None
    premature_stop_rate: float | None
    gap_through_frequency: float | None
    mean_gap_loss_pct: float | None
    tail_loss_p05: float | None
    average_holding_period_sessions: float | None
    median_mae_before_exit: float | None
    median_mfe_full_horizon: float | None
    mean_initial_risk_pct: float | None


@dataclass(frozen=True, slots=True)
class StopResearchComparison:
    """One fixed-horizon risk-policy comparison with explicit interpretation boundary."""

    horizon: int
    complete_event_count: int
    success_criterion: str
    cost_model_version: str
    entry_slippage_bps: float
    exit_slippage_bps: float
    policy_summaries: tuple[StopPolicySummary, ...]
    warnings: tuple[str, ...]
    research_state: str = "EXPLORATORY"
    comparison_definition_version: str = "stop-policy-comparison-v0.1"


def summarize_stop_policy_results(
    results: tuple[RiskPolicyResult, ...],
    *,
    policies: tuple[StopPolicy, ...],
    horizon: int,
    entry_slippage_bps: float,
    exit_slippage_bps: float,
) -> StopResearchComparison:
    """Aggregate event-level results while retaining every tested policy."""

    if horizon < 1:
        raise ValueError("stop comparison horizon must be positive")
    if not policies:
        raise ValueError("stop comparison requires at least one policy")
    if len({item.policy_id for item in policies}) != len(policies):
        raise ValueError("stop policy IDs must be unique")
    if any(item.horizon != horizon for item in results):
        raise ValueError("stop comparison cannot mix outcome horizons")

    by_policy: dict[str, list[RiskPolicyResult]] = {item.policy_id: [] for item in policies}
    for result in results:
        if result.risk_policy_id not in by_policy:
            raise ValueError(f"result references unknown stop policy {result.risk_policy_id}")
        by_policy[result.risk_policy_id].append(result)

    no_stop_policy = next(
        (item for item in policies if item.family is StopFamily.NO_STOP),
        None,
    )
    if no_stop_policy is None:
        raise ValueError("stop comparison requires a no-stop baseline")
    no_stop_results = tuple(by_policy[no_stop_policy.policy_id])
    no_stop_mean = _mean(tuple(item.realized_return for item in no_stop_results))
    complete_event_count = len(no_stop_results)

    summaries = tuple(
        _summary(
            policy,
            tuple(by_policy[policy.policy_id]),
            no_stop_mean=no_stop_mean,
        )
        for policy in policies
    )
    counts = {item.sample_size for item in summaries}
    warnings = [
        (
            "Stop policies are applied after event detection; they do not change which "
            "breakouts existed."
        ),
        (
            "Premature stop means a stopped event still finished positive at the selected "
            "no-stop horizon."
        ),
        (
            "Daily-bar stop-only simulations have no stop/target ordering ambiguity, but "
            "intraday path is not observed."
        ),
        (
            "Exploratory policy grids are exposed to multiple-testing risk and are not "
            "production stop recommendations."
        ),
    ]
    if len(counts) != 1:
        warnings.append(
            "Policy sample sizes differ; inspect incomplete or unavailable event-level results."
        )
    if entry_slippage_bps == 0 and exit_slippage_bps == 0:
        warnings.append(
            "Execution costs are zero; positive expectancy is gross exploratory evidence only."
        )

    cost_versions = {item.cost_model_version for item in results}
    cost_version = next(iter(cost_versions)) if len(cost_versions) == 1 else "mixed"
    return StopResearchComparison(
        horizon=horizon,
        complete_event_count=complete_event_count,
        success_criterion="positive no-stop net return at the selected research horizon",
        cost_model_version=cost_version,
        entry_slippage_bps=entry_slippage_bps,
        exit_slippage_bps=exit_slippage_bps,
        policy_summaries=summaries,
        warnings=tuple(warnings),
    )


def _summary(
    policy: StopPolicy,
    results: tuple[RiskPolicyResult, ...],
    *,
    no_stop_mean: float | None,
) -> StopPolicySummary:
    returns = tuple(item.realized_return for item in results)
    winners = tuple(value for value in returns if value > 0)
    losers = tuple(value for value in returns if value < 0)
    stopped = tuple(item for item in results if item.stop_out)
    gaps = tuple(item for item in stopped if item.gap_through_stop)
    r_values = tuple(item.realized_r for item in results if item.realized_r is not None)
    risks = tuple(item.initial_risk_pct for item in results if item.initial_risk_pct is not None)
    expectancy = _mean(returns)
    return StopPolicySummary(
        policy_id=policy.policy_id,
        policy_version=policy.version,
        stop_family=policy.family,
        resolved_parameters=policy.parameters,
        sample_size=len(results),
        stop_out_count=len(stopped),
        stop_out_rate=len(stopped) / len(results) if results else 0.0,
        expectancy=expectancy,
        expectancy_delta_vs_no_stop=(
            expectancy - no_stop_mean
            if expectancy is not None and no_stop_mean is not None
            else None
        ),
        median_return=median(returns) if returns else None,
        win_probability=sum(value > 0 for value in returns) / len(returns) if returns else None,
        average_winner=_mean(winners),
        median_winner=median(winners) if winners else None,
        average_loser=_mean(losers),
        median_loser=median(losers) if losers else None,
        profit_factor=_profit_factor(winners, losers),
        average_r=_mean(r_values),
        median_r=median(r_values) if r_values else None,
        premature_stop_rate=(
            sum(item.premature_stop_flag for item in stopped) / len(stopped) if stopped else None
        ),
        gap_through_frequency=len(gaps) / len(stopped) if stopped else None,
        mean_gap_loss_pct=_mean(tuple(item.gap_loss_pct for item in gaps)),
        tail_loss_p05=_quantile(tuple(sorted(returns)), 0.05) if returns else None,
        average_holding_period_sessions=_mean(
            tuple(float(item.holding_period_sessions) for item in results)
        ),
        median_mae_before_exit=(
            median(item.mae_before_exit for item in results) if results else None
        ),
        median_mfe_full_horizon=(
            median(item.mfe_full_horizon for item in results) if results else None
        ),
        mean_initial_risk_pct=_mean(tuple(float(value) for value in risks)),
    )


def _mean(values: tuple[float, ...]) -> float | None:
    return sum(values) / len(values) if values else None


def _profit_factor(winners: tuple[float, ...], losers: tuple[float, ...]) -> float | None:
    if not losers:
        return None
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
    "StopPolicySummary",
    "StopResearchComparison",
    "summarize_stop_policy_results",
]
