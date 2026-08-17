"""Strategy-neutral post-entry exit policy engine.

The event layer decides whether a setup existed. This module only evaluates what happens after a
pre-existing event using provider-neutral ``ResearchBar`` values. Policies are configuration data,
not strategy-specific code, so the same exit logic can be reused by future setup families.

Daily-bar trailing semantics are deliberately conservative: a trailing stop for session *t* is
computed only from information available through the end of session *t-1*. A new intraday high on
session *t* can tighten the stop for session *t+1*, but is never assumed to occur before that same
session's low. This avoids inventing intraday ordering from OHLC bars.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.risk.initial_stops import CostModel, pre_entry_atr


class ExitFamily(StrEnum):
    """Reusable long-position exit families supported by the first generic exit engine."""

    HOLD_TO_HORIZON = "hold_to_horizon"
    FIXED_PERCENT_STOP = "fixed_percent_stop"
    ATR_STOP = "atr_stop"
    TRAILING_PERCENT_STOP = "trailing_percent_stop"
    TRAILING_ATR_STOP = "trailing_atr_stop"


class ExitReason(StrEnum):
    """Why one simulated position terminated."""

    RESEARCH_HORIZON = "research_horizon"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    """Resolved versioned exit rule independent of the entry/setup implementation."""

    policy_id: str
    family: ExitFamily
    parameters: Mapping[str, float]
    version: str = "generic-exit-policy-v0.1"

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("exit policy identity and version must be non-empty")
        parameters = MappingProxyType(dict(self.parameters))
        object.__setattr__(self, "parameters", parameters)
        if self.family is ExitFamily.HOLD_TO_HORIZON:
            if parameters:
                raise ValueError("hold-to-horizon policy accepts no parameters")
            return
        parameter_name = (
            "distance_pct"
            if self.family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP}
            else "atr_multiple"
        )
        if set(parameters) != {parameter_name}:
            raise ValueError(f"{self.family.value} requires only {parameter_name}")
        if parameters[parameter_name] <= 0:
            raise ValueError(f"{parameter_name} must be positive")
        if parameter_name == "distance_pct" and parameters[parameter_name] >= 1:
            raise ValueError("distance_pct must be less than 100%")


@dataclass(frozen=True, slots=True)
class ExitPolicyResult:
    """Event-level path result produced by one generic exit policy."""

    event_id: str
    instrument_id: str
    policy_id: str
    policy_version: str
    family: ExitFamily
    resolved_parameters: Mapping[str, float]
    horizon: int
    entry_date: str
    market_entry_price: float
    assumed_entry_price: float
    initial_stop: float | None
    final_active_stop: float | None
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
    gap_through_stop: bool
    gap_loss_pct: float
    holding_period_sessions: int
    mae_before_exit: float
    mfe_full_horizon: float
    max_drawdown_before_exit: float
    dataset_version: str
    execution_semantics_version: str = "daily-bar-prior-session-trailing-v0.1"
    result_definition_version: str = "generic-exit-policy-result-v0.1"


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
    """Build a deterministic policy family from operator-supplied parameter grids."""

    _validate_grid(fixed_percentages, "fixed_percentages", upper=1.0)
    _validate_grid(atr_multiples, "atr_multiples")
    _validate_grid(trailing_percentages, "trailing_percentages", upper=1.0)
    _validate_grid(trailing_atr_multiples, "trailing_atr_multiples")
    policies: list[ExitPolicy] = [
        ExitPolicy(
            policy_id="hold-to-horizon",
            family=ExitFamily.HOLD_TO_HORIZON,
            parameters=MappingProxyType({}),
        )
    ]
    policies.extend(
        ExitPolicy(
            policy_id=f"fixed-stop-{_pct_id(value)}",
            family=ExitFamily.FIXED_PERCENT_STOP,
            parameters=MappingProxyType({"distance_pct": value}),
        )
        for value in fixed_percentages
    )
    policies.extend(
        ExitPolicy(
            policy_id=f"atr-stop-{multiple:g}x",
            family=ExitFamily.ATR_STOP,
            parameters=MappingProxyType({"atr_multiple": multiple}),
        )
        for multiple in atr_multiples
    )
    policies.extend(
        ExitPolicy(
            policy_id=f"trailing-stop-{_pct_id(value)}",
            family=ExitFamily.TRAILING_PERCENT_STOP,
            parameters=MappingProxyType({"distance_pct": value}),
        )
        for value in trailing_percentages
    )
    policies.extend(
        ExitPolicy(
            policy_id=f"trailing-atr-{multiple:g}x",
            family=ExitFamily.TRAILING_ATR_STOP,
            parameters=MappingProxyType({"atr_multiple": multiple}),
        )
        for multiple in trailing_atr_multiples
    )
    if len({item.policy_id for item in policies}) != len(policies):
        raise ValueError("resolved exit policy IDs must be unique")
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
    if policy.family in {ExitFamily.ATR_STOP, ExitFamily.TRAILING_ATR_STOP}:
        atr = pre_entry_atr(bars, signal_index=event.signal_index)
        if atr is None:
            return None

    initial_stop = _initial_stop(market_entry, policy, atr)
    if initial_stop is None:
        return _build_result(
            event=event,
            policy=policy,
            path=path,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=None,
            final_stop=None,
            peak_prior=market_entry,
            exit_offset=horizon - 1,
            market_exit=horizon_exit,
            assumed_exit=assumed_horizon_exit,
            exit_reason=ExitReason.RESEARCH_HORIZON,
            gap_through=False,
            gap_loss_pct=0.0,
            no_policy_return=no_policy_return,
            cost_model=cost_model,
        )

    active_stop = initial_stop
    peak_through_prior_session = market_entry
    for offset, bar in enumerate(path):
        hit = _stop_fill(bar, active_stop, market_entry)
        if hit is not None:
            market_exit, gap_through, gap_loss_pct = hit
            assumed_exit = _apply_exit_costs(market_exit, cost_model, stop_exit=True)
            return _build_result(
                event=event,
                policy=policy,
                path=path,
                entry_bar=entry_bar,
                assumed_entry=assumed_entry,
                initial_stop=initial_stop,
                final_stop=active_stop,
                peak_prior=peak_through_prior_session,
                exit_offset=offset,
                market_exit=market_exit,
                assumed_exit=assumed_exit,
                exit_reason=ExitReason.STOP,
                gap_through=gap_through,
                gap_loss_pct=gap_loss_pct,
                no_policy_return=no_policy_return,
                cost_model=cost_model,
            )
        peak_through_prior_session = max(peak_through_prior_session, bar.high)
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
        peak_prior=peak_through_prior_session,
        exit_offset=horizon - 1,
        market_exit=horizon_exit,
        assumed_exit=assumed_horizon_exit,
        exit_reason=ExitReason.RESEARCH_HORIZON,
        gap_through=False,
        gap_loss_pct=0.0,
        no_policy_return=no_policy_return,
        cost_model=cost_model,
    )


def evaluate_exit_policy_grid(
    bars: tuple[ResearchBar, ...],
    events: tuple[EventRecord, ...],
    *,
    horizon: int,
    policies: tuple[ExitPolicy, ...],
    cost_model: CostModel = _DEFAULT_COST_MODEL,
) -> tuple[ExitPolicyResult, ...]:
    """Evaluate a complete policy family on an exact common event population.

    Series-wide invariants are checked once per instrument batch rather than once for every
    event-policy pair. This preserves the direct-call safety of ``evaluate_exit_policy`` while
    avoiding repeated O(history) validation in large Strategy Builder runs.
    """

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
) -> tuple[float, bool, float] | None:
    if bar.open <= stop:
        market_exit = bar.open
        return market_exit, True, max(0.0, (stop - market_exit) / market_entry)
    if bar.low <= stop:
        return stop, False, 0.0
    return None


def _build_result(
    *,
    event: EventRecord,
    policy: ExitPolicy,
    path: tuple[ResearchBar, ...],
    entry_bar: ResearchBar,
    assumed_entry: float,
    initial_stop: float | None,
    final_stop: float | None,
    peak_prior: float,
    exit_offset: int,
    market_exit: float,
    assumed_exit: float,
    exit_reason: ExitReason,
    gap_through: bool,
    gap_loss_pct: float,
    no_policy_return: float,
    cost_model: CostModel,
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
        horizon=len(path),
        entry_date=entry_bar.trade_date.isoformat(),
        market_entry_price=market_entry,
        assumed_entry_price=assumed_entry,
        initial_stop=initial_stop,
        final_active_stop=final_stop,
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
    "evaluate_exit_policy",
    "evaluate_exit_policy_grid",
    "exit_policy_grid",
]
