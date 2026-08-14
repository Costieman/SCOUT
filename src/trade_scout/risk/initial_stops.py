"""Baseline protective-stop research applied to an already-defined event population.

The risk layer never decides whether an event existed. It receives immutable EventRecord values
and the same provider-neutral ResearchBar history used by the outcome layer, then simulates simple
protective policies under explicit daily-bar fill semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.features.initial import ATR_FEATURE_NAME, ATR_FEATURE_VERSION, ATR_PERIOD
from trade_scout.patterns.contracts import PatternState


class StopFamily(StrEnum):
    """Version 1 simple stop families enabled for exploratory comparison."""

    NO_STOP = "no_stop"
    FIXED_PERCENT = "fixed_percent"
    ATR = "atr"
    STRUCTURAL_BASE_LOW = "structural_base_low"
    STRUCTURAL_BOUNDARY = "structural_boundary"
    HYBRID_STRUCTURAL_ATR = "hybrid_structural_atr"


class RiskExitReason(StrEnum):
    """Why one simulated risk policy terminated the position."""

    RESEARCH_HORIZON = "research_horizon"
    STOP = "stop"
    ENTRY_AT_OR_BELOW_STOP = "entry_at_or_below_stop"


class PrematureStopSuccessKind(StrEnum):
    """Predeclared success definitions used only to diagnose stopped events."""

    HORIZON_RETURN = "horizon_return"
    POST_STOP_MFE = "post_stop_mfe"


class PrematureStopStatus(StrEnum):
    """Whether a stop removed an event that later met the fixed success definition."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO = "NO"
    YES = "YES"
    SAME_BAR_AMBIGUOUS = "SAME_BAR_AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class PrematureStopDefinition:
    """Frozen research definition used to calculate premature-stop diagnostics."""

    definition_id: str = "positive-horizon-return"
    kind: PrematureStopSuccessKind = PrematureStopSuccessKind.HORIZON_RETURN
    threshold_return: float = 0.0
    version: str = "premature-stop-success-v0.2"

    def __post_init__(self) -> None:
        if not self.definition_id.strip() or not self.version.strip():
            raise ValueError("premature-stop definition identity and version must be non-empty")
        if self.threshold_return <= -1:
            raise ValueError("premature-stop return threshold must be greater than -100%")
        if self.kind is PrematureStopSuccessKind.POST_STOP_MFE and self.threshold_return <= 0:
            raise ValueError("post-stop MFE success threshold must be positive")


_DEFAULT_PREMATURE_SUCCESS = PrematureStopDefinition()


@dataclass(frozen=True, slots=True)
class CostModel:
    """Explicit execution-cost hooks for exploratory policy comparison."""

    entry_slippage_bps: float = 0.0
    exit_slippage_bps: float = 0.0
    stop_slippage_bps: float = 0.0
    commission_bps_per_side: float = 0.0
    version: str = "explicit-bps-cost-v0.2"

    def __post_init__(self) -> None:
        values = (
            self.entry_slippage_bps,
            self.exit_slippage_bps,
            self.stop_slippage_bps,
            self.commission_bps_per_side,
        )
        if any(value < 0 for value in values):
            raise ValueError("cost and slippage assumptions must be non-negative")
        if not self.version.strip():
            raise ValueError("cost model version must be non-empty")


_DEFAULT_COST_MODEL = CostModel()


@dataclass(frozen=True, slots=True)
class StructuralStopContext:
    """Pattern-neutral structural geometry required by structural risk policies."""

    event_id: str
    formation_start: date
    formation_end: date
    support: float
    resistance: float
    dataset_version: str
    pattern_instance_id: str | None = None
    context_version: str = "structural-stop-context-v0.1"

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.dataset_version.strip():
            raise ValueError("structural context event and dataset identity must be non-empty")
        if self.formation_start > self.formation_end:
            raise ValueError("structural context formation dates are reversed")
        if self.support <= 0 or self.resistance <= 0 or self.support > self.resistance:
            raise ValueError("structural context support/resistance are invalid")
        if not self.context_version.strip():
            raise ValueError("structural context version must be non-empty")


@runtime_checkable
class _LegacyStructuralEvent(EventRecord, Protocol):
    """Compatibility surface for the exploratory pre-PatternState event."""

    @property
    def duration(self) -> int: ...

    @property
    def boundary(self) -> float: ...

    @property
    def formation_start(self) -> date: ...

    @property
    def formation_end(self) -> date: ...


@dataclass(frozen=True, slots=True)
class StopPolicy:
    """Resolved, versioned initial protective-stop definition."""

    policy_id: str
    family: StopFamily
    parameters: Mapping[str, float]
    version: str = "initial-stop-policy-v0.2"

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("stop policy identity and version must be non-empty")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if self.family is StopFamily.FIXED_PERCENT:
            _positive_parameter(self.parameters, "distance_pct")
        elif self.family is StopFamily.ATR:
            _positive_parameter(self.parameters, "atr_multiple")
        elif self.family is StopFamily.STRUCTURAL_BOUNDARY:
            if set(self.parameters) - {"atr_buffer_multiple"}:
                raise ValueError("structural boundary accepts only atr_buffer_multiple")
            value = self.parameters.get("atr_buffer_multiple", 0.0)
            if value < 0:
                raise ValueError("structural ATR buffer must be non-negative")
        elif self.family is StopFamily.HYBRID_STRUCTURAL_ATR:
            _positive_parameter(self.parameters, "atr_multiple")
        elif self.parameters:
            raise ValueError(f"{self.family.value} does not accept parameters")


@dataclass(frozen=True, slots=True)
class RiskPolicyResult:
    """Event-level result from applying one risk policy to one fixed research horizon."""

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
    gross_realized_return: float
    realized_return: float
    cost_drag_return: float
    initial_risk_pct: float | None
    realized_r: float | None
    stop_out: bool
    premature_stop_flag: bool
    premature_stop_status: PrematureStopStatus
    premature_success_definition_id: str
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
    atr_definition_version: str = f"{ATR_FEATURE_NAME}:{ATR_FEATURE_VERSION}"
    result_definition_version: str = "risk-policy-result-v0.2"


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


def structural_stop_context_from_pattern_state(
    event: EventRecord,
    pattern: PatternState,
) -> StructuralStopContext:
    """Build risk geometry from the generic PatternState contract without importing a detector."""

    if pattern.instrument_id != event.instrument_id:
        raise ValueError("pattern and event must reference the same instrument")
    if pattern.dataset_version != event.dataset_version:
        raise ValueError("pattern and event must reference the same dataset version")
    if pattern.formation_end >= event.signal_date:
        raise ValueError("risk structural context must be known before the event signal")
    support = pattern.structural_boundaries.get("support")
    resistance = pattern.structural_boundaries.get("resistance")
    if support is None or resistance is None:
        raise ValueError("structural stop context requires support and resistance boundaries")
    return StructuralStopContext(
        event_id=event.event_id,
        formation_start=pattern.formation_start,
        formation_end=pattern.formation_end,
        support=support,
        resistance=resistance,
        dataset_version=pattern.dataset_version,
        pattern_instance_id=pattern.pattern_instance_id,
    )


def evaluate_stop_policy(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
    *,
    horizon: int,
    policy: StopPolicy,
    cost_model: CostModel = _DEFAULT_COST_MODEL,
    structural_context: StructuralStopContext | None = None,
    premature_success: PrematureStopDefinition = _DEFAULT_PREMATURE_SUCCESS,
) -> RiskPolicyResult | None:
    """Apply one policy after one event without changing event membership.

    ``None`` means the selected forward horizon is incomplete or contains unusable rows. All
    policies in a comparison must therefore operate on the same complete-horizon event subset.
    """

    if horizon < 1:
        raise ValueError("risk horizon must be positive")
    _validate_event_series(bars, event)
    resolved_context = _resolve_structural_context(bars, event, structural_context)
    entry_index = event.signal_index + 1
    exit_index = entry_index + horizon - 1
    if entry_index >= len(bars) or exit_index >= len(bars):
        return None
    path = bars[entry_index : exit_index + 1]
    if any(not _usable(item) for item in path):
        return None

    entry_bar = bars[entry_index]
    entry_market = entry_bar.open
    assumed_entry = _apply_entry_costs(entry_market, cost_model)
    horizon_market_exit = path[-1].close
    no_stop_exit = _apply_exit_costs(horizon_market_exit, cost_model, stop_exit=False)
    no_stop_return = no_stop_exit / assumed_entry - 1.0
    stop = _initial_stop(
        bars,
        event,
        entry_market=entry_market,
        policy=policy,
        structural_context=resolved_context,
    )

    if stop is None:
        return _result(
            event=event,
            policy=policy,
            horizon=horizon,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=None,
            stop_trigger_date=None,
            exit_bar=path[-1],
            market_exit=horizon_market_exit,
            assumed_exit=no_stop_exit,
            exit_reason=RiskExitReason.RESEARCH_HORIZON,
            stop_out=False,
            premature_status=PrematureStopStatus.NOT_APPLICABLE,
            premature_success=premature_success,
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
        market_exit = entry_market
        assumed_exit = _apply_exit_costs(market_exit, cost_model, stop_exit=True)
        premature_status = _classify_premature_stop(
            full_path=path,
            stop_offset=0,
            entry_market=entry_market,
            no_stop_return=no_stop_return,
            definition=premature_success,
        )
        entry_flags = ["ENTRY_AT_OR_BELOW_INITIAL_STOP"]
        if premature_status is PrematureStopStatus.SAME_BAR_AMBIGUOUS:
            entry_flags.append("STOP_AND_SUCCESS_THRESHOLD_SAME_BAR_ORDER_UNKNOWN")
        return _result(
            event=event,
            policy=policy,
            horizon=horizon,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=stop,
            stop_trigger_date=entry_bar.trade_date.isoformat(),
            exit_bar=entry_bar,
            market_exit=market_exit,
            assumed_exit=assumed_exit,
            exit_reason=RiskExitReason.ENTRY_AT_OR_BELOW_STOP,
            stop_out=True,
            premature_status=premature_status,
            premature_success=premature_success,
            gap_through=False,
            gap_loss_pct=0.0,
            exit_offset=0,
            path_to_exit=(entry_bar,),
            full_path=path,
            no_stop_return=no_stop_return,
            ambiguity_flags=tuple(entry_flags),
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
        assumed_exit = _apply_exit_costs(market_exit, cost_model, stop_exit=True)
        premature_status = _classify_premature_stop(
            full_path=path,
            stop_offset=offset,
            entry_market=entry_market,
            no_stop_return=no_stop_return,
            definition=premature_success,
        )
        stop_flags: tuple[str, ...] = ()
        if premature_status is PrematureStopStatus.SAME_BAR_AMBIGUOUS:
            stop_flags = ("STOP_AND_SUCCESS_THRESHOLD_SAME_BAR_ORDER_UNKNOWN",)
        return _result(
            event=event,
            policy=policy,
            horizon=horizon,
            entry_bar=entry_bar,
            assumed_entry=assumed_entry,
            initial_stop=stop,
            stop_trigger_date=bar.trade_date.isoformat(),
            exit_bar=bar,
            market_exit=market_exit,
            assumed_exit=assumed_exit,
            exit_reason=RiskExitReason.STOP,
            stop_out=True,
            premature_status=premature_status,
            premature_success=premature_success,
            gap_through=gap_through,
            gap_loss_pct=gap_loss_pct,
            exit_offset=offset,
            path_to_exit=path[: offset + 1],
            full_path=path,
            no_stop_return=no_stop_return,
            ambiguity_flags=stop_flags,
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
        market_exit=horizon_market_exit,
        assumed_exit=no_stop_exit,
        exit_reason=RiskExitReason.RESEARCH_HORIZON,
        stop_out=False,
        premature_status=PrematureStopStatus.NOT_APPLICABLE,
        premature_success=premature_success,
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
    events: tuple[EventRecord, ...],
    *,
    horizon: int,
    policies: tuple[StopPolicy, ...] | None = None,
    cost_model: CostModel = _DEFAULT_COST_MODEL,
    structural_contexts: Mapping[str, StructuralStopContext] | None = None,
    premature_success: PrematureStopDefinition = _DEFAULT_PREMATURE_SUCCESS,
) -> tuple[RiskPolicyResult, ...]:
    """Evaluate every policy on every event using one common eligible event population."""

    resolved = policies or initial_stop_policy_grid()
    if not resolved:
        raise ValueError("at least one stop policy is required")
    if len({policy.policy_id for policy in resolved}) != len(resolved):
        raise ValueError("stop policy IDs must be unique")

    atr_required = any(_policy_requires_atr(item) for item in resolved)
    structural_required = any(_policy_requires_structure(item) for item in resolved)
    results: list[RiskPolicyResult] = []
    for event in events:
        if atr_required and pre_entry_atr(bars, signal_index=event.signal_index) is None:
            continue
        supplied_context = (
            structural_contexts.get(event.event_id) if structural_contexts is not None else None
        )
        resolved_context = _resolve_structural_context(bars, event, supplied_context)
        if structural_required and resolved_context is None:
            raise ValueError(
                f"structural policies require structural context for event {event.event_id}"
            )
        event_results = [
            evaluate_stop_policy(
                bars,
                event,
                horizon=horizon,
                policy=policy,
                cost_model=cost_model,
                structural_context=resolved_context,
                premature_success=premature_success,
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


def _policy_requires_atr(policy: StopPolicy) -> bool:
    if policy.family in {StopFamily.ATR, StopFamily.HYBRID_STRUCTURAL_ATR}:
        return True
    return (
        policy.family is StopFamily.STRUCTURAL_BOUNDARY
        and policy.parameters.get("atr_buffer_multiple", 0.0) > 0
    )


def _policy_requires_structure(policy: StopPolicy) -> bool:
    return policy.family in {
        StopFamily.STRUCTURAL_BASE_LOW,
        StopFamily.STRUCTURAL_BOUNDARY,
        StopFamily.HYBRID_STRUCTURAL_ATR,
    }


def _initial_stop(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
    *,
    entry_market: float,
    policy: StopPolicy,
    structural_context: StructuralStopContext | None,
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

    if structural_context is None:
        raise ValueError(f"{policy.family.value} requires structural stop context")
    if policy.family is StopFamily.STRUCTURAL_BASE_LOW:
        return structural_context.support
    if policy.family is StopFamily.STRUCTURAL_BOUNDARY:
        buffer_multiple = policy.parameters.get("atr_buffer_multiple", 0.0)
        if buffer_multiple == 0:
            return structural_context.resistance
        if atr is None:
            raise ValueError("buffered structural stop requires sufficient pre-entry ATR history")
        return structural_context.resistance - buffer_multiple * atr
    if policy.family is StopFamily.HYBRID_STRUCTURAL_ATR:
        if atr is None:
            raise ValueError("hybrid structural/ATR stop requires sufficient pre-entry ATR history")
        atr_stop = entry_market - policy.parameters["atr_multiple"] * atr
        # Baseline hybrid is deliberately explicit: use the wider (lower) of structure and ATR.
        return min(structural_context.support, atr_stop)
    raise AssertionError(f"unhandled stop family {policy.family}")


def _result(
    *,
    event: EventRecord,
    policy: StopPolicy,
    horizon: int,
    entry_bar: ResearchBar,
    assumed_entry: float,
    initial_stop: float | None,
    stop_trigger_date: str | None,
    exit_bar: ResearchBar,
    market_exit: float,
    assumed_exit: float,
    exit_reason: RiskExitReason,
    stop_out: bool,
    premature_status: PrematureStopStatus,
    premature_success: PrematureStopDefinition,
    gap_through: bool,
    gap_loss_pct: float,
    exit_offset: int,
    path_to_exit: tuple[ResearchBar, ...],
    full_path: tuple[ResearchBar, ...],
    no_stop_return: float,
    ambiguity_flags: tuple[str, ...],
    cost_model: CostModel,
) -> RiskPolicyResult:
    market_entry = entry_bar.open
    gross_realized_return = market_exit / market_entry - 1.0
    realized_return = assumed_exit / assumed_entry - 1.0
    cost_drag = gross_realized_return - realized_return
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
        gross_realized_return=gross_realized_return,
        realized_return=realized_return,
        cost_drag_return=cost_drag,
        initial_risk_pct=initial_risk_pct,
        realized_r=realized_r,
        stop_out=stop_out,
        premature_stop_flag=premature_status is PrematureStopStatus.YES,
        premature_stop_status=premature_status,
        premature_success_definition_id=(
            f"{premature_success.definition_id}:{premature_success.version}"
        ),
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


def _classify_premature_stop(
    *,
    full_path: tuple[ResearchBar, ...],
    stop_offset: int,
    entry_market: float,
    no_stop_return: float,
    definition: PrematureStopDefinition,
) -> PrematureStopStatus:
    if definition.kind is PrematureStopSuccessKind.HORIZON_RETURN:
        return (
            PrematureStopStatus.YES
            if no_stop_return > definition.threshold_return
            else PrematureStopStatus.NO
        )

    success_price = entry_market * (1.0 + definition.threshold_return)
    stop_bar = full_path[stop_offset]
    if stop_bar.high >= success_price:
        return PrematureStopStatus.SAME_BAR_AMBIGUOUS
    if any(bar.high >= success_price for bar in full_path[stop_offset + 1 :]):
        return PrematureStopStatus.YES
    return PrematureStopStatus.NO


def _resolve_structural_context(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
    supplied: StructuralStopContext | None,
) -> StructuralStopContext | None:
    if supplied is not None:
        if supplied.event_id != event.event_id:
            raise ValueError("structural context event_id does not match event")
        if supplied.dataset_version != event.dataset_version:
            raise ValueError("structural context dataset version does not match event")
        if supplied.formation_end >= event.signal_date:
            raise ValueError("structural context must be fixed before the event signal")
        return supplied

    if not isinstance(event, _LegacyStructuralEvent):
        return None
    formation = bars[event.signal_index - event.duration : event.signal_index]
    if len(formation) != event.duration:
        raise ValueError("structural stop requires the complete event formation window")
    return StructuralStopContext(
        event_id=event.event_id,
        formation_start=event.formation_start,
        formation_end=event.formation_end,
        support=min(item.low for item in formation),
        resistance=event.boundary,
        dataset_version=event.dataset_version,
    )


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _apply_entry_costs(price: float, model: CostModel) -> float:
    bps = model.entry_slippage_bps + model.commission_bps_per_side
    return price * (1.0 + bps / 10_000.0)


def _apply_exit_costs(price: float, model: CostModel, *, stop_exit: bool) -> float:
    bps = model.exit_slippage_bps + model.commission_bps_per_side
    if stop_exit:
        bps += model.stop_slippage_bps
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
    event: EventRecord,
) -> None:
    if not bars:
        raise ValueError("risk evaluation requires research bars")
    if event.signal_index < 0 or event.signal_index >= len(bars):
        raise ValueError("event signal index is outside supplied research bars")

    instruments = {bar.instrument_id for bar in bars}
    dataset_versions = {str(bar.dataset_version) for bar in bars}
    representations = {bar.price_representation for bar in bars}
    if len(instruments) != 1:
        raise ValueError("risk evaluation requires one instrument")
    if len(dataset_versions) != 1:
        raise ValueError("risk evaluation requires one dataset version")
    if len(representations) != 1:
        raise ValueError("risk evaluation cannot mix price representations")
    dates = [bar.trade_date for bar in bars]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("risk bars must be unique and date-increasing")

    signal = bars[event.signal_index]
    if signal.instrument_id != event.instrument_id or signal.trade_date != event.signal_date:
        raise ValueError("event identity/date does not match supplied research series")
    if str(signal.dataset_version) != event.dataset_version:
        raise ValueError("event and research bars use different dataset versions")
    if not _usable(signal):
        raise ValueError("event signal bar must be eligible and quality PASS")


__all__ = [
    "ATR_STOP_GRID",
    "FIXED_STOP_GRID",
    "CostModel",
    "PrematureStopDefinition",
    "PrematureStopStatus",
    "PrematureStopSuccessKind",
    "RiskExitReason",
    "RiskPolicyResult",
    "StopFamily",
    "StopPolicy",
    "StructuralStopContext",
    "evaluate_stop_policy",
    "evaluate_stop_policy_grid",
    "initial_stop_policy_grid",
    "pre_entry_atr",
    "structural_stop_context_from_pattern_state",
]
