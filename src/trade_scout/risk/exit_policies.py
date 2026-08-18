"""Strategy-neutral post-entry exit policy engine.

The event layer decides whether a setup existed. This module only evaluates what happens after a
pre-existing event using provider-neutral ``ResearchBar`` values. Policies are configuration data,
not strategy-specific code, so the same exit logic can be reused by future setup families.

Daily-bar trailing semantics are deliberately conservative: a trailing stop for session *t* is
computed only from information available through the end of session *t-1*. A new intraday high on
session *t* can tighten the stop for session *t+1*, but is never assumed to occur before that same
session's low. Stop/target ordering inside one daily OHLC bar is also explicit rather than silently
invented.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.risk.initial_stops import CostModel, pre_entry_atr


class ExitFamily(StrEnum):
    """Reusable long-position protective-stop families supported by the generic exit engine."""

    HOLD_TO_HORIZON = "hold_to_horizon"
    FIXED_PERCENT_STOP = "fixed_percent_stop"
    ATR_STOP = "atr_stop"
    TRAILING_PERCENT_STOP = "trailing_percent_stop"
    TRAILING_ATR_STOP = "trailing_atr_stop"


class TargetFamily(StrEnum):
    """Profit-target components that may be paired with one protective stop."""

    FIXED_PERCENT = "fixed_percent_target"
    ATR_MULTIPLE = "atr_multiple_target"
    R_MULTIPLE = "r_multiple_target"


class SameBarExitPolicy(StrEnum):
    """Explicit ordering assumption when a daily bar touches both stop and target."""

    STOP_FIRST = "stop_first"
    TARGET_FIRST = "target_first"


class ExitReason(StrEnum):
    """Why one simulated position terminated."""

    RESEARCH_HORIZON = "research_horizon"
    STOP = "stop"
    TARGET = "target"


@dataclass(frozen=True, slots=True)
class ManagedExitPlan:
    """User-facing managed exit: one protective stop plus an optional profit target.

    The research horizon is always the final backstop. The plan exits on the first configured stop
    or target trigger before that backstop. Partial position scaling is intentionally outside this
    first contract because it requires position-leg accounting rather than one terminal exit.
    """

    stop_family: ExitFamily
    stop_value: float
    target_family: TargetFamily | None = None
    target_value: float | None = None
    same_bar_policy: SameBarExitPolicy = SameBarExitPolicy.STOP_FIRST

    def __post_init__(self) -> None:
        if self.stop_family is ExitFamily.HOLD_TO_HORIZON:
            raise ValueError("managed exit plans require a protective stop")
        _validate_stop_value(self.stop_family, self.stop_value)
        if (self.target_family is None) != (self.target_value is None):
            raise ValueError("target family and target value must be supplied together")
        if self.target_family is not None and self.target_value is not None:
            _validate_target_value(self.target_family, self.target_value)


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    """Resolved versioned exit rule independent of the entry/setup implementation."""

    policy_id: str
    family: ExitFamily
    parameters: Mapping[str, float]
    target_family: TargetFamily | None = None
    target_parameters: Mapping[str, float] = field(default_factory=dict)
    same_bar_policy: SameBarExitPolicy = SameBarExitPolicy.STOP_FIRST
    version: str = "generic-exit-policy-v0.2"

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("exit policy identity and version must be non-empty")
        parameters = MappingProxyType(dict(self.parameters))
        target_parameters = MappingProxyType(dict(self.target_parameters))
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "target_parameters", target_parameters)
        _validate_policy_stop(self.family, parameters)
        _validate_policy_target(self.family, self.target_family, target_parameters)


@dataclass(frozen=True, slots=True)
class ExitPolicyResult:
    """Event-level path result produced by one generic exit policy."""

    event_id: str
    instrument_id: str
    policy_id: str
    policy_version: str
    family: ExitFamily
    resolved_parameters: Mapping[str, float]
    target_family: TargetFamily | None
    target_parameters: Mapping[str, float]
    same_bar_policy: SameBarExitPolicy
    horizon: int
    entry_date: str
    market_entry_price: float
    assumed_entry_price: float
    initial_stop: float | None
    final_active_stop: float | None
    initial_target: float | None
    peak_price_through_prior_session: float
    exit_date: str
    market_exit_price: float
    assumed_exit_price: float
    exit_reason: ExitReason
    gross_realized_return: float
    realized_return: float
    no_exit_policy_horizon_return: float
    cost_drag_return: float
    stopped: bool
    targeted: bool
    same_bar_stop_target_ambiguous: bool
    gap_through_stop: bool
    gap_loss_pct: float
    holding_period_sessions: int
    mae_before_exit: float
    mfe_full_horizon: float
    max_drawdown_before_exit: float
    dataset_version: str
    execution_semantics_version: str = "daily-bar-composite-exit-v0.2"
    result_definition_version: str = "generic-exit-policy-result-v0.2"


DEFAULT_FIXED_PERCENT_GRID = (0.02, 0.03, 0.04, 0.05, 0.07, 0.10)
DEFAULT_ATR_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)
DEFAULT_TRAILING_PERCENT_GRID = (0.02, 0.03, 0.05, 0.07, 0.10)
DEFAULT_TRAILING_ATR_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)
_DEFAULT_COST_MODEL = CostModel()


def exit_policy_grid(
    *,
    fixed_percentages: tuple[float, ...] = DEFAULT_FIXED_PERCENT_GRID,
    atr_multiples: tuple[float, ...] = DEFAULT_ATR_GRID,
    trailing_percentages: tuple[float, ...] = DEFAULT_TRAILING_PERCENT_GRID,
    trailing_atr_multiples: tuple[float, ...] = DEFAULT_TRAILING_ATR_GRID,
) -> tuple[ExitPolicy, ...]:
    """Build the legacy stop-only comparison grid plus its hold-to-horizon control."""

    _validate_grid(fixed_percentages, "fixed_percentages", upper=1.0)
    _validate_grid(atr_multiples, "atr_multiples")
    _validate_grid(trailing_percentages, "trailing_percentages", upper=1.0)
    _validate_grid(trailing_atr_multiples, "trailing_atr_multiples")
    policies: list[ExitPolicy] = [_hold_policy()]
    policies.extend(
        ExitPolicy(
            policy_id=f"fixed-stop-{_pct_id(value)}",
            family=ExitFamily.FIXED_PERCENT_STOP,
            parameters={"distance_pct": value},
        )
        for value in fixed_percentages
    )
    policies.extend(
        ExitPolicy(
            policy_id=f"atr-stop-{multiple:g}x",
            family=ExitFamily.ATR_STOP,
            parameters={"atr_multiple": multiple},
        )
        for multiple in atr_multiples
    )
    policies.extend(
        ExitPolicy(
            policy_id=f"trailing-stop-{_pct_id(value)}",
            family=ExitFamily.TRAILING_PERCENT_STOP,
            parameters={"distance_pct": value},
        )
        for value in trailing_percentages
    )
    policies.extend(
        ExitPolicy(
            policy_id=f"trailing-atr-{multiple:g}x",
            family=ExitFamily.TRAILING_ATR_STOP,
            parameters={"atr_multiple": multiple},
        )
        for multiple in trailing_atr_multiples
    )
    _validate_unique_policy_ids(policies)
    return tuple(policies)


def managed_exit_policy_grid(
    plans: tuple[ManagedExitPlan, ...],
    *,
    include_hold_control: bool = True,
) -> tuple[ExitPolicy, ...]:
    """Materialize explicit stop-plus-target plans without creating a Cartesian search."""

    if len(set(plans)) != len(plans):
        raise ValueError("managed exit plans must not contain duplicates")
    policies: list[ExitPolicy] = [_hold_policy()] if include_hold_control else []
    policies.extend(_policy_from_plan(plan) for plan in plans)
    if not policies:
        raise ValueError("managed exit policy grid requires at least one policy")
    _validate_unique_policy_ids(policies)
    return tuple(policies)


def evaluate_exit_policy(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
    *,
    horizon: int,
    policy: ExitPolicy,
    cost_model: CostModel = _DEFAULT_COST_MODEL,
) -> ExitPolicyResult | None:
    """Apply one exit policy to one already-defined event.

    ``None`` means the complete forward horizon is unavailable or contains unusable rows. The
    caller should compare policies only on the common complete event population.
    """

    if horizon < 1:
        raise ValueError("exit-policy horizon must be positive")
    _validate_event_series(bars, event)
    return _evaluate_exit_policy_validated(
        bars,
        event,
        horizon=horizon,
        policy=policy,
        cost_model=cost_model,
    )


def _evaluate_exit_policy_validated(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
    *,
    horizon: int,
    policy: ExitPolicy,
    cost_model: CostModel,
) -> ExitPolicyResult | None:
    entry_index = event.signal_index + 1
    exit_index = entry_index + horizon - 1
    if entry_index >= len(bars) or exit_index >= len(bars):
        return None
    path = bars[entry_index : exit_index + 1]
    if any(not _usable(item) for item in path):
        return None

    entry_bar = bars[entry_index]
    market_entry = entry_bar.open
    assumed_entry = _apply_entry_costs(market_entry, cost_model)
    horizon_exit = path[-1].close
    assumed_horizon_exit = _apply_exit_costs(horizon_exit, cost_model, stop_exit=False)
    no_policy_return = assumed_horizon_exit / assumed_entry - 1.0

    atr = None
    if _policy_requires_atr(policy):
        atr = pre_entry_atr(bars, signal_index=event.signal_index)
        if atr is None:
            return None

    initial_stop = _initial_stop(market_entry, policy, atr)
    initial_target = _initial_target(market_entry, policy, atr, initial_stop)
    if initial_stop is None and initial_target is None:
        return _build_result(
            event=event,
            policy=policy,
            path=path,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=None,
            final_stop=None,
            initial_target=None,
            peak_prior=market_entry,
            exit_offset=horizon - 1,
            market_exit=horizon_exit,
            assumed_exit=assumed_horizon_exit,
            exit_reason=ExitReason.RESEARCH_HORIZON,
            same_bar_ambiguous=False,
            gap_through=False,
            gap_loss_pct=0.0,
            no_policy_return=no_policy_return,
        )

    active_stop = initial_stop
    peak_through_prior_session = market_entry
    for offset, bar in enumerate(path):
        stop_hit = (
            _stop_fill(bar, active_stop, market_entry) if active_stop is not None else None
        )
        target_hit = _target_fill(bar, initial_target) if initial_target is not None else None
        if stop_hit is not None or target_hit is not None:
            selected, ambiguous = _select_exit_hit(
                stop_hit=stop_hit,
                target_hit=target_hit,
                policy=policy.same_bar_policy,
            )
            reason, market_exit, gap_through, gap_loss_pct = selected
            assumed_exit = _apply_exit_costs(
                market_exit,
                cost_model,
                stop_exit=reason is ExitReason.STOP,
            )
            return _build_result(
                event=event,
                policy=policy,
                path=path,
                entry_bar=entry_bar,
                assumed_entry=assumed_entry,
                initial_stop=initial_stop,
                final_stop=active_stop,
                initial_target=initial_target,
                peak_prior=peak_through_prior_session,
                exit_offset=offset,
                market_exit=market_exit,
                assumed_exit=assumed_exit,
                exit_reason=reason,
                same_bar_ambiguous=ambiguous,
                gap_through=gap_through,
                gap_loss_pct=gap_loss_pct,
                no_policy_return=no_policy_return,
            )
        peak_through_prior_session = max(peak_through_prior_session, bar.high)
        if active_stop is not None:
            active_stop = _next_session_stop(
                current_stop=active_stop,
                peak=peak_through_prior_session,
                policy=policy,
                atr=atr,
            )

    return _build_result(
        event=event,
        policy=policy,
        path=path,
        entry_bar=entry_bar,
        assumed_entry=assumed_entry,
        initial_stop=initial_stop,
        final_stop=active_stop,
        initial_target=initial_target,
        peak_prior=peak_through_prior_session,
        exit_offset=horizon - 1,
        market_exit=horizon_exit,
        assumed_exit=assumed_horizon_exit,
        exit_reason=ExitReason.RESEARCH_HORIZON,
        same_bar_ambiguous=False,
        gap_through=False,
        gap_loss_pct=0.0,
        no_policy_return=no_policy_return,
    )


def evaluate_exit_policy_grid(
    bars: tuple[ResearchBar, ...],
    events: tuple[EventRecord, ...],
    *,
    horizon: int,
    policies: tuple[ExitPolicy, ...],
    cost_model: CostModel = _DEFAULT_COST_MODEL,
) -> tuple[ExitPolicyResult, ...]:
    """Evaluate a complete policy family on an exact common event population."""

    if horizon < 1:
        raise ValueError("exit-policy horizon must be positive")
    if not policies:
        raise ValueError("at least one exit policy is required")
    if len({item.policy_id for item in policies}) != len(policies):
        raise ValueError("exit policy IDs must be unique")
    _validate_series(bars)

    results: list[ExitPolicyResult] = []
    for event in events:
        _validate_event_against_series(bars, event)
        event_results = tuple(
            _evaluate_exit_policy_validated(
                bars,
                event,
                horizon=horizon,
                policy=policy,
                cost_model=cost_model,
            )
            for policy in policies
        )
        if any(item is None for item in event_results):
            continue
        results.extend(item for item in event_results if item is not None)
    return tuple(results)


def _hold_policy() -> ExitPolicy:
    return ExitPolicy(
        policy_id="hold-to-horizon",
        family=ExitFamily.HOLD_TO_HORIZON,
        parameters={},
    )


def _policy_from_plan(plan: ManagedExitPlan) -> ExitPolicy:
    parameters = _stop_parameters(plan.stop_family, plan.stop_value)
    target_parameters = (
        _target_parameters(plan.target_family, plan.target_value)
        if plan.target_family is not None and plan.target_value is not None
        else {}
    )
    target_id = (
        "no-target"
        if plan.target_family is None
        else _target_id(plan.target_family, plan.target_value)
    )
    return ExitPolicy(
        policy_id=(
            f"managed-{_stop_id(plan.stop_family, plan.stop_value)}-{target_id}-"
            f"{plan.same_bar_policy.value}"
        ),
        family=plan.stop_family,
        parameters=parameters,
        target_family=plan.target_family,
        target_parameters=target_parameters,
        same_bar_policy=plan.same_bar_policy,
    )


def _policy_requires_atr(policy: ExitPolicy) -> bool:
    return policy.family in {ExitFamily.ATR_STOP, ExitFamily.TRAILING_ATR_STOP} or (
        policy.target_family is TargetFamily.ATR_MULTIPLE
    )


def _initial_stop(
    entry: float,
    policy: ExitPolicy,
    atr: float | None,
) -> float | None:
    if policy.family is ExitFamily.HOLD_TO_HORIZON:
        return None
    if policy.family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP}:
        return entry * (1.0 - policy.parameters["distance_pct"])
    if atr is None:
        raise ValueError("ATR-based exit policy requires pre-entry ATR")
    return entry - policy.parameters["atr_multiple"] * atr


def _initial_target(
    entry: float,
    policy: ExitPolicy,
    atr: float | None,
    initial_stop: float | None,
) -> float | None:
    if policy.target_family is None:
        return None
    if policy.target_family is TargetFamily.FIXED_PERCENT:
        return entry * (1.0 + policy.target_parameters["gain_pct"])
    if policy.target_family is TargetFamily.ATR_MULTIPLE:
        if atr is None:
            raise ValueError("ATR target requires pre-entry ATR")
        return entry + policy.target_parameters["atr_multiple"] * atr
    if initial_stop is None:
        raise ValueError("R-multiple target requires an initial protective stop")
    initial_risk = entry - initial_stop
    if initial_risk <= 0:
        raise ValueError("R-multiple target requires positive initial risk")
    return entry + policy.target_parameters["r_multiple"] * initial_risk


def _next_session_stop(
    *,
    current_stop: float,
    peak: float,
    policy: ExitPolicy,
    atr: float | None,
) -> float:
    if policy.family is ExitFamily.TRAILING_PERCENT_STOP:
        return max(current_stop, peak * (1.0 - policy.parameters["distance_pct"]))
    if policy.family is ExitFamily.TRAILING_ATR_STOP:
        if atr is None:
            raise ValueError("trailing ATR policy requires pre-entry ATR")
        return max(current_stop, peak - policy.parameters["atr_multiple"] * atr)
    return current_stop


def _stop_fill(
    bar: ResearchBar,
    stop: float,
    market_entry: float,
) -> tuple[ExitReason, float, bool, float] | None:
    if bar.open <= stop:
        market_exit = bar.open
        gap_loss_pct = max(0.0, (stop - market_exit) / market_entry)
        return ExitReason.STOP, market_exit, True, gap_loss_pct
    if bar.low <= stop:
        return ExitReason.STOP, stop, False, 0.0
    return None


def _target_fill(
    bar: ResearchBar,
    target: float,
) -> tuple[ExitReason, float, bool, float] | None:
    if bar.open >= target:
        return ExitReason.TARGET, bar.open, False, 0.0
    if bar.high >= target:
        return ExitReason.TARGET, target, False, 0.0
    return None


def _select_exit_hit(
    *,
    stop_hit: tuple[ExitReason, float, bool, float] | None,
    target_hit: tuple[ExitReason, float, bool, float] | None,
    policy: SameBarExitPolicy,
) -> tuple[tuple[ExitReason, float, bool, float], bool]:
    if stop_hit is None and target_hit is None:
        raise ValueError("exit-hit selector requires a stop or target hit")
    if stop_hit is None:
        assert target_hit is not None
        return target_hit, False
    if target_hit is None:
        return stop_hit, False
    if stop_hit[2]:
        return stop_hit, False
    if target_hit[1] != stop_hit[1] and target_hit[1] > stop_hit[1]:
        selected = stop_hit if policy is SameBarExitPolicy.STOP_FIRST else target_hit
        return selected, True
    selected = stop_hit if policy is SameBarExitPolicy.STOP_FIRST else target_hit
    return selected, True


def _build_result(
    *,
    event: EventRecord,
    policy: ExitPolicy,
    path: tuple[ResearchBar, ...],
    entry_bar: ResearchBar,
    assumed_entry: float,
    initial_stop: float | None,
    final_stop: float | None,
    initial_target: float | None,
    peak_prior: float,
    exit_offset: int,
    market_exit: float,
    assumed_exit: float,
    exit_reason: ExitReason,
    same_bar_ambiguous: bool,
    gap_through: bool,
    gap_loss_pct: float,
    no_policy_return: float,
) -> ExitPolicyResult:
    market_entry = entry_bar.open
    realized_return = assumed_exit / assumed_entry - 1.0
    gross_return = market_exit / market_entry - 1.0
    path_to_exit = path[: exit_offset + 1]
    mae = min(item.low / market_entry - 1.0 for item in path_to_exit)
    mfe = max(item.high / market_entry - 1.0 for item in path)
    return ExitPolicyResult(
        event_id=event.event_id,
        instrument_id=str(event.instrument_id),
        policy_id=policy.policy_id,
        policy_version=policy.version,
        family=policy.family,
        resolved_parameters=policy.parameters,
        target_family=policy.target_family,
        target_parameters=policy.target_parameters,
        same_bar_policy=policy.same_bar_policy,
        horizon=len(path),
        entry_date=entry_bar.trade_date.isoformat(),
        market_entry_price=market_entry,
        assumed_entry_price=assumed_entry,
        initial_stop=initial_stop,
        final_active_stop=final_stop,
        initial_target=initial_target,
        peak_price_through_prior_session=peak_prior,
        exit_date=path[exit_offset].trade_date.isoformat(),
        market_exit_price=market_exit,
        assumed_exit_price=assumed_exit,
        exit_reason=exit_reason,
        gross_realized_return=gross_return,
        realized_return=realized_return,
        no_exit_policy_horizon_return=no_policy_return,
        cost_drag_return=gross_return - realized_return,
        stopped=exit_reason is ExitReason.STOP,
        targeted=exit_reason is ExitReason.TARGET,
        same_bar_stop_target_ambiguous=same_bar_ambiguous,
        gap_through_stop=gap_through,
        gap_loss_pct=gap_loss_pct,
        holding_period_sessions=exit_offset + 1,
        mae_before_exit=mae,
        mfe_full_horizon=mfe,
        max_drawdown_before_exit=_max_drawdown(path_to_exit, market_entry),
        dataset_version=event.dataset_version,
    )


def _max_drawdown(path: tuple[ResearchBar, ...], entry: float) -> float:
    peak = entry
    worst = 0.0
    for bar in path:
        peak = max(peak, bar.high)
        worst = min(worst, bar.low / peak - 1.0)
    return worst


def _apply_entry_costs(price: float, model: CostModel) -> float:
    bps = model.entry_slippage_bps + model.commission_bps_per_side
    return price * (1.0 + bps / 10_000.0)


def _apply_exit_costs(price: float, model: CostModel, *, stop_exit: bool) -> float:
    bps = model.exit_slippage_bps + model.commission_bps_per_side
    if stop_exit:
        bps += model.stop_slippage_bps
    return price * (1.0 - bps / 10_000.0)


def _validate_policy_stop(family: ExitFamily, parameters: Mapping[str, float]) -> None:
    if family is ExitFamily.HOLD_TO_HORIZON:
        if parameters:
            raise ValueError("hold-to-horizon policy accepts no stop parameters")
        return
    parameter_name = (
        "distance_pct"
        if family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP}
        else "atr_multiple"
    )
    if set(parameters) != {parameter_name}:
        raise ValueError(f"{family.value} requires only {parameter_name}")
    _validate_stop_value(family, parameters[parameter_name])


def _validate_policy_target(
    family: ExitFamily,
    target_family: TargetFamily | None,
    parameters: Mapping[str, float],
) -> None:
    if target_family is None:
        if parameters:
            raise ValueError("target parameters require a target family")
        return
    parameter_name = {
        TargetFamily.FIXED_PERCENT: "gain_pct",
        TargetFamily.ATR_MULTIPLE: "atr_multiple",
        TargetFamily.R_MULTIPLE: "r_multiple",
    }[target_family]
    if set(parameters) != {parameter_name}:
        raise ValueError(f"{target_family.value} requires only {parameter_name}")
    _validate_target_value(target_family, parameters[parameter_name])
    if target_family is TargetFamily.R_MULTIPLE and family is ExitFamily.HOLD_TO_HORIZON:
        raise ValueError("R-multiple target requires a protective stop")


def _validate_stop_value(family: ExitFamily, value: float) -> None:
    if value <= 0:
        raise ValueError("protective stop value must be positive")
    if family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP} and value >= 1:
        raise ValueError("percentage protective stop must be below 100%")


def _validate_target_value(family: TargetFamily, value: float) -> None:
    if value <= 0:
        raise ValueError("profit target value must be positive")
    if family is TargetFamily.FIXED_PERCENT and value >= 10:
        raise ValueError("fixed percentage profit target must be below 1000%")


def _stop_parameters(family: ExitFamily, value: float) -> dict[str, float]:
    return (
        {"distance_pct": value}
        if family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP}
        else {"atr_multiple": value}
    )


def _target_parameters(family: TargetFamily, value: float) -> dict[str, float]:
    name = {
        TargetFamily.FIXED_PERCENT: "gain_pct",
        TargetFamily.ATR_MULTIPLE: "atr_multiple",
        TargetFamily.R_MULTIPLE: "r_multiple",
    }[family]
    return {name: value}


def _stop_id(family: ExitFamily, value: float) -> str:
    if family is ExitFamily.FIXED_PERCENT_STOP:
        return f"fixed-stop-{_pct_id(value)}"
    if family is ExitFamily.TRAILING_PERCENT_STOP:
        return f"trailing-stop-{_pct_id(value)}"
    if family is ExitFamily.ATR_STOP:
        return f"atr-stop-{value:g}x"
    if family is ExitFamily.TRAILING_ATR_STOP:
        return f"trailing-atr-{value:g}x"
    raise ValueError("managed exit plan requires a protective stop family")


def _target_id(family: TargetFamily, value: float | None) -> str:
    if value is None:
        raise ValueError("target ID requires a value")
    if family is TargetFamily.FIXED_PERCENT:
        return f"target-{_pct_id(value)}"
    if family is TargetFamily.ATR_MULTIPLE:
        return f"target-atr-{value:g}x"
    return f"target-{value:g}r"


def _validate_unique_policy_ids(policies: list[ExitPolicy]) -> None:
    if len({item.policy_id for item in policies}) != len(policies):
        raise ValueError("resolved exit policy IDs must be unique")


def _validate_event_series(bars: tuple[ResearchBar, ...], event: EventRecord) -> None:
    _validate_series(bars)
    _validate_event_against_series(bars, event)


def _validate_series(bars: tuple[ResearchBar, ...]) -> None:
    if not bars:
        raise ValueError("exit-policy evaluation requires research bars")
    instruments = {bar.instrument_id for bar in bars}
    versions = {str(bar.dataset_version) for bar in bars}
    representations = {bar.price_representation for bar in bars}
    if len(instruments) != 1:
        raise ValueError("exit-policy evaluation requires one instrument")
    if len(versions) != 1:
        raise ValueError("exit-policy bars must use one dataset version")
    if len(representations) != 1:
        raise ValueError("exit-policy evaluation cannot mix price representations")
    dates = tuple(bar.trade_date for bar in bars)
    if dates != tuple(sorted(dates)) or len(set(dates)) != len(dates):
        raise ValueError("exit-policy bars must be unique and date-increasing")


def _validate_event_against_series(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
) -> None:
    if event.signal_index < 0 or event.signal_index >= len(bars):
        raise ValueError("event signal index is outside supplied research bars")
    signal = bars[event.signal_index]
    if signal.instrument_id != event.instrument_id:
        raise ValueError("exit-policy evaluation requires one matching instrument")
    if str(signal.dataset_version) != event.dataset_version:
        raise ValueError("event and exit-policy bars must use one dataset version")
    if signal.trade_date != event.signal_date:
        raise ValueError("event signal date/index does not match supplied bars")
    if not _usable(signal):
        raise ValueError("event signal bar must be eligible and quality PASS")


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _validate_grid(values: tuple[float, ...], field: str, *, upper: float | None = None) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    if any(value <= 0 for value in values):
        raise ValueError(f"{field} values must be positive")
    if upper is not None and any(value >= upper for value in values):
        raise ValueError(f"{field} values must be below {upper}")


def _pct_id(value: float) -> str:
    return f"{value * 100:g}pct".replace(".", "p")


__all__ = [
    "DEFAULT_ATR_GRID",
    "DEFAULT_FIXED_PERCENT_GRID",
    "DEFAULT_TRAILING_ATR_GRID",
    "DEFAULT_TRAILING_PERCENT_GRID",
    "ExitFamily",
    "ExitPolicy",
    "ExitPolicyResult",
    "ExitReason",
    "ManagedExitPlan",
    "SameBarExitPolicy",
    "TargetFamily",
    "evaluate_exit_policy",
    "evaluate_exit_policy_grid",
    "exit_policy_grid",
    "managed_exit_policy_grid",
]
