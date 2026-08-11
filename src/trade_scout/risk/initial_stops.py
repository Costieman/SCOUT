"""Baseline protective-stop research applied to an already-defined event population.

The risk layer never decides whether a breakout existed. It receives immutable breakout events
and the same provider-neutral ResearchBar history used by the outcome layer, then simulates simple
protective policies under explicit daily-bar fill semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.features.initial import ATR_FEATURE_VERSION, ATR_PERIOD
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutEvent


class StopFamily(StrEnum):
    """Version 1 simple stop families enabled for exploratory comparison."""

    NO_STOP = "no_stop"
    FIXED_PERCENT = "fixed_percent"
    ATR = "atr"
    STRUCTURAL_BASE_LOW = "structural_base_low"
    STRUCTURAL_BOUNDARY = "structural_boundary"


class RiskExitReason(StrEnum):
    """Why one simulated risk policy terminated the position."""

    RESEARCH_HORIZON = "research_horizon"
    STOP = "stop"
    ENTRY_AT_OR_BELOW_STOP = "entry_at_or_below_stop"


@dataclass(frozen=True, slots=True)
class CostModel:
    """Simple explicit execution-cost assumptions for exploratory stop comparison."""

    entry_slippage_bps: float = 0.0
    exit_slippage_bps: float = 0.0
    version: str = "simple-bps-cost-v0.1"

    def __post_init__(self) -> None:
        if self.entry_slippage_bps < 0 or self.exit_slippage_bps < 0:
            raise ValueError("slippage assumptions must be non-negative")
        if not self.version.strip():
            raise ValueError("cost model version must be non-empty")


@dataclass(frozen=True, slots=True)
class StopPolicy:
    """Resolved, versioned initial protective-stop definition."""

    policy_id: str
    family: StopFamily
    parameters: Mapping[str, float]
    version: str = "initial-stop-policy-v0.1"

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("stop policy identity and version must be non-empty")
        if self.family is StopFamily.FIXED_PERCENT:
            _positive_parameter(self.parameters, "distance_pct")
        elif self.family is StopFamily.ATR:
            _positive_parameter(self.parameters, "atr_multiple")
        elif self.family is StopFamily.STRUCTURAL_BOUNDARY:
            value = self.parameters.get("atr_buffer_multiple", 0.0)
            if value < 0:
                raise ValueError("structural ATR buffer must be non-negative")
        elif self.parameters:
            raise ValueError(f"{self.family.value} does not accept parameters")


@dataclass(frozen=True, slots=True)
class RiskPolicyResult:
    """Event-level result from applying one stop policy to one fixed research horizon."""

    event_id: str
    instrument_id: str
    risk_policy_id: str
    risk_policy_version: str
    stop_family: StopFamily
    resolved_parameters: Mapping[str, float]
    horizon: int
    entry_date: str
    entry_price: float
    assumed_entry_price: float
    initial_stop: float | None
    stop_trigger_date: str | None
    exit_date: str
    assumed_exit_price: float
    exit_reason: RiskExitReason
    realized_return: float
    initial_risk_pct: float | None
    realized_r: float | None
    stop_out: bool
    premature_stop_flag: bool
    gap_through_stop: bool
    gap_loss_pct: float
    holding_period_sessions: int
    mae_before_exit: float
    mfe_full_horizon: float
    post_stop_mfe: float | None
    no_stop_horizon_return: float
    ambiguity_flags: tuple[str, ...]
    cost_model_version: str
    dataset_version: str
    atr_definition_version: str = ATR_FEATURE_VERSION
    result_definition_version: str = "risk-policy-result-v0.1"


FIXED_STOP_GRID = (0.02, 0.03, 0.04, 0.05, 0.07, 0.10)
ATR_STOP_GRID = (1.0, 1.5, 2.0, 2.5, 3.0)


def initial_stop_policy_grid() -> tuple[StopPolicy, ...]:
    """Return the simple Version 1 exploratory policy grid from the research specification."""

    policies = [
        StopPolicy(
            policy_id="no-stop-horizon",
            family=StopFamily.NO_STOP,
            parameters=MappingProxyType({}),
        )
    ]
    policies.extend(
        StopPolicy(
            policy_id=f"fixed-{int(distance * 100)}pct",
            family=StopFamily.FIXED_PERCENT,
            parameters=MappingProxyType({"distance_pct": distance}),
        )
        for distance in FIXED_STOP_GRID
    )
    policies.extend(
        StopPolicy(
            policy_id=f"atr-{multiple:g}x",
            family=StopFamily.ATR,
            parameters=MappingProxyType({"atr_multiple": multiple}),
        )
        for multiple in ATR_STOP_GRID
    )
    policies.extend(
        (
            StopPolicy(
                policy_id="structural-base-low",
                family=StopFamily.STRUCTURAL_BASE_LOW,
                parameters=MappingProxyType({}),
            ),
            StopPolicy(
                policy_id="structural-boundary",
                family=StopFamily.STRUCTURAL_BOUNDARY,
                parameters=MappingProxyType({"atr_buffer_multiple": 0.0}),
            ),
            StopPolicy(
                policy_id="structural-boundary-0.5atr-buffer",
                family=StopFamily.STRUCTURAL_BOUNDARY,
                parameters=MappingProxyType({"atr_buffer_multiple": 0.5}),
            ),
        )
    )
    return tuple(policies)


def evaluate_stop_policy(
    bars: tuple[ResearchBar, ...],
    event: ConsolidationBreakoutEvent,
    *,
    horizon: int,
    policy: StopPolicy,
    cost_model: CostModel = CostModel(),
) -> RiskPolicyResult | None:
    """Apply one policy after one event without changing event membership.

    ``None`` means the selected forward horizon is incomplete or contains unusable rows. All
    policies therefore operate on the same complete-horizon event subset.
    """

    if horizon < 1:
        raise ValueError("risk horizon must be positive")
    _validate_event_series(bars, event)
    entry_index = event.signal_index + 1
    exit_index = entry_index + horizon - 1
    if entry_index >= len(bars) or exit_index >= len(bars):
        return None
    path = bars[entry_index : exit_index + 1]
    if any(not _usable(item) for item in path):
        return None

    entry_bar = bars[entry_index]
    entry_market = entry_bar.open
    assumed_entry = _apply_entry_slippage(entry_market, cost_model.entry_slippage_bps)
    horizon_market_exit = path[-1].close
    no_stop_exit = _apply_exit_slippage(horizon_market_exit, cost_model.exit_slippage_bps)
    no_stop_return = no_stop_exit / assumed_entry - 1.0
    stop = _initial_stop(bars, event, entry_market=entry_market, policy=policy)

    if stop is None:
        exit_bar = path[-1]
        assumed_exit = no_stop_exit
        return _result(
            event=event,
            policy=policy,
            horizon=horizon,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=None,
            stop_trigger_date=None,
            exit_bar=exit_bar,
            assumed_exit=assumed_exit,
            exit_reason=RiskExitReason.RESEARCH_HORIZON,
            stop_out=False,
            premature=False,
            gap_through=False,
            gap_loss_pct=0.0,
            exit_offset=horizon - 1,
            path_to_exit=path,
            full_path=path,
            no_stop_return=no_stop_return,
            ambiguity_flags=(),
            cost_model=cost_model,
        )

    if stop >= entry_market:
        assumed_exit = _apply_exit_slippage(entry_market, cost_model.exit_slippage_bps)
        return _result(
            event=event,
            policy=policy,
            horizon=horizon,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=stop,
            stop_trigger_date=entry_bar.trade_date.isoformat(),
            exit_bar=entry_bar,
            assumed_exit=assumed_exit,
            exit_reason=RiskExitReason.ENTRY_AT_OR_BELOW_STOP,
            stop_out=True,
            premature=no_stop_return > 0,
            gap_through=False,
            gap_loss_pct=0.0,
            exit_offset=0,
            path_to_exit=(entry_bar,),
            full_path=path,
            no_stop_return=no_stop_return,
            ambiguity_flags=("ENTRY_AT_OR_BELOW_INITIAL_STOP",),
            cost_model=cost_model,
        )

    for offset, bar in enumerate(path):
        if bar.open <= stop:
            market_exit = bar.open
            gap_through = True
            gap_loss_pct = (stop - market_exit) / entry_market
        elif bar.low <= stop:
            market_exit = stop
            gap_through = False
            gap_loss_pct = 0.0
        else:
            continue
        assumed_exit = _apply_exit_slippage(market_exit, cost_model.exit_slippage_bps)
        return _result(
            event=event,
            policy=policy,
            horizon=horizon,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=stop,
            stop_trigger_date=bar.trade_date.isoformat(),
            exit_bar=bar,
            assumed_exit=assumed_exit,
            exit_reason=RiskExitReason.STOP,
            stop_out=True,
            premature=no_stop_return > 0,
            gap_through=gap_through,
            gap_loss_pct=gap_loss_pct,
            exit_offset=offset,
            path_to_exit=path[: offset + 1],
            full_path=path,
            no_stop_return=no_stop_return,
            ambiguity_flags=(),
            cost_model=cost_model,
        )

    return _result(
        event=event,
        policy=policy,
        horizon=horizon,
        entry_bar=entry_bar,
        assumed_entry=assumed_entry,
        initial_stop=stop,
        stop_trigger_date=None,
        exit_bar=path[-1],
        assumed_exit=no_stop_exit,
        exit_reason=RiskExitReason.RESEARCH_HORIZON,
        stop_out=False,
        premature=False,
        gap_through=False,
        gap_loss_pct=0.0,
        exit_offset=horizon - 1,
        path_to_exit=path,
        full_path=path,
        no_stop_return=no_stop_return,
        ambiguity_flags=(),
        cost_model=cost_model,
    )


def evaluate_stop_policy_grid(
    bars: tuple[ResearchBar, ...],
    events: tuple[ConsolidationBreakoutEvent, ...],
    *,
    horizon: int,
    policies: tuple[StopPolicy, ...] | None = None,
    cost_model: CostModel = CostModel(),
) -> tuple[RiskPolicyResult, ...]:
    """Evaluate every policy on every event with a complete common forward horizon."""

    resolved = policies or initial_stop_policy_grid()
    if not resolved:
        raise ValueError("at least one stop policy is required")
    results: list[RiskPolicyResult] = []
    for event in events:
        event_results = [
            evaluate_stop_policy(
                bars,
                event,
                horizon=horizon,
                policy=policy,
                cost_model=cost_model,
            )
            for policy in resolved
        ]
        if any(item is None for item in event_results):
            continue
        results.extend(item for item in event_results if item is not None)
    return tuple(results)


def pre_entry_atr(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    period: int = ATR_PERIOD,
) -> float | None:
    """Simple mean true range ending on the signal date, using no post-signal information."""

    if period < 1:
        raise ValueError("ATR period must be positive")
    if signal_index < period or signal_index >= len(bars):
        return None
    true_ranges: list[float] = []
    for index in range(signal_index - period + 1, signal_index + 1):
        current = bars[index]
        previous = bars[index - 1]
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return sum(true_ranges) / period


def _initial_stop(
    bars: tuple[ResearchBar, ...],
    event: ConsolidationBreakoutEvent,
    *,
    entry_market: float,
    policy: StopPolicy,
) -> float | None:
    if policy.family is StopFamily.NO_STOP:
        return None
    if policy.family is StopFamily.FIXED_PERCENT:
        return entry_market * (1.0 - policy.parameters["distance_pct"])

    atr = pre_entry_atr(bars, signal_index=event.signal_index)
    if policy.family is StopFamily.ATR:
        if atr is None:
            raise ValueError("ATR stop requires sufficient pre-entry ATR history")
        return entry_market - policy.parameters["atr_multiple"] * atr

    formation = bars[event.signal_index - event.duration : event.signal_index]
    if len(formation) != event.duration:
        raise ValueError("structural stop requires the complete event formation window")
    if policy.family is StopFamily.STRUCTURAL_BASE_LOW:
        return min(item.low for item in formation)
    if policy.family is StopFamily.STRUCTURAL_BOUNDARY:
        buffer_multiple = policy.parameters.get("atr_buffer_multiple", 0.0)
        if buffer_multiple == 0:
            return event.boundary
        if atr is None:
            raise ValueError("buffered structural stop requires sufficient pre-entry ATR history")
        return event.boundary - buffer_multiple * atr
    raise AssertionError(f"unhandled stop family {policy.family}")


def _result(
    *,
    event: ConsolidationBreakoutEvent,
    policy: StopPolicy,
    horizon: int,
    entry_bar: ResearchBar,
    assumed_entry: float,
    initial_stop: float | None,
    stop_trigger_date: str | None,
    exit_bar: ResearchBar,
    assumed_exit: float,
    exit_reason: RiskExitReason,
    stop_out: bool,
    premature: bool,
    gap_through: bool,
    gap_loss_pct: float,
    exit_offset: int,
    path_to_exit: tuple[ResearchBar, ...],
    full_path: tuple[ResearchBar, ...],
    no_stop_return: float,
    ambiguity_flags: tuple[str, ...],
    cost_model: CostModel,
) -> RiskPolicyResult:
    realized_return = assumed_exit / assumed_entry - 1.0
    market_entry = entry_bar.open
    initial_risk_pct = (
        (market_entry - initial_stop) / market_entry
        if initial_stop is not None and initial_stop < market_entry
        else None
    )
    realized_r = (
        realized_return / initial_risk_pct
        if initial_risk_pct is not None and initial_risk_pct > 0
        else None
    )
    mae = min(item.low / market_entry - 1.0 for item in path_to_exit)
    mfe = max(item.high / market_entry - 1.0 for item in full_path)
    post_stop_mfe = None
    if stop_out:
        remaining = full_path[exit_offset:]
        post_stop_mfe = max(item.high / market_entry - 1.0 for item in remaining)

    return RiskPolicyResult(
        event_id=event.event_id,
        instrument_id=str(event.instrument_id),
        risk_policy_id=policy.policy_id,
        risk_policy_version=policy.version,
        stop_family=policy.family,
        resolved_parameters=policy.parameters,
        horizon=horizon,
        entry_date=entry_bar.trade_date.isoformat(),
        entry_price=market_entry,
        assumed_entry_price=assumed_entry,
        initial_stop=initial_stop,
        stop_trigger_date=stop_trigger_date,
        exit_date=exit_bar.trade_date.isoformat(),
        assumed_exit_price=assumed_exit,
        exit_reason=exit_reason,
        realized_return=realized_return,
        initial_risk_pct=initial_risk_pct,
        realized_r=realized_r,
        stop_out=stop_out,
        premature_stop_flag=premature,
        gap_through_stop=gap_through,
        gap_loss_pct=gap_loss_pct,
        holding_period_sessions=exit_offset + 1,
        mae_before_exit=mae,
        mfe_full_horizon=mfe,
        post_stop_mfe=post_stop_mfe,
        no_stop_horizon_return=no_stop_return,
        ambiguity_flags=ambiguity_flags,
        cost_model_version=cost_model.version,
        dataset_version=event.dataset_version,
    )


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _apply_entry_slippage(price: float, bps: float) -> float:
    return price * (1.0 + bps / 10_000.0)


def _apply_exit_slippage(price: float, bps: float) -> float:
    return price * (1.0 - bps / 10_000.0)


def _positive_parameter(parameters: Mapping[str, float], name: str) -> float:
    if set(parameters) != {name}:
        raise ValueError(f"stop policy requires only {name}")
    value = parameters[name]
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_event_series(
    bars: tuple[ResearchBar, ...],
    event: ConsolidationBreakoutEvent,
) -> None:
    if not bars:
        raise ValueError("risk evaluation requires research bars")
    if event.signal_index < 0 or event.signal_index >= len(bars):
        raise ValueError("event signal index is outside supplied research bars")
    signal = bars[event.signal_index]
    if signal.instrument_id != event.instrument_id or signal.trade_date != event.signal_date:
        raise ValueError("event identity/date does not match supplied research series")
    if str(signal.dataset_version) != event.dataset_version:
        raise ValueError("event and research bars use different dataset versions")


__all__ = [
    "ATR_STOP_GRID",
    "FIXED_STOP_GRID",
    "CostModel",
    "RiskExitReason",
    "RiskPolicyResult",
    "StopFamily",
    "StopPolicy",
    "evaluate_stop_policy",
    "evaluate_stop_policy_grid",
    "initial_stop_policy_grid",
    "pre_entry_atr",
]
