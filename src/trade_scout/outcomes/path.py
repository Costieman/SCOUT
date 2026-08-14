"""Canonical post-event path measurement with explicit ambiguity and truncation.

The outcome layer starts after an already-defined event. It never changes whether the event
existed and it does not apply stop, target, or position-management rules. Close-confirmed events
enter at the next observed session open. Daily OHLC bars are treated as order-unknown within each
session, so drawdown is reported as a deterministic interval rather than by inventing intraday
sequencing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import (
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events.contracts import EventRecord


class OutcomePathStatus(StrEnum):
    """Completion state for one event and requested forward horizon."""

    COMPLETE = "COMPLETE"
    NO_ENTRY_BAR = "NO_ENTRY_BAR"
    ENTRY_UNUSABLE = "ENTRY_UNUSABLE"
    TRUNCATED_END_OF_DATA = "TRUNCATED_END_OF_DATA"
    TRUNCATED_UNUSABLE_BAR = "TRUNCATED_UNUSABLE_BAR"


class ExtremeOrder(StrEnum):
    """Observable ordering of the horizon-wide favorable and adverse extremes."""

    MFE_BEFORE_MAE = "MFE_BEFORE_MAE"
    MAE_BEFORE_MFE = "MAE_BEFORE_MFE"
    SAME_BAR_AMBIGUOUS = "SAME_BAR_AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class OutcomePath:
    """One event/horizon path under next-session-open entry semantics.

    ``max_drawdown_lower_bound`` is the more severe value obtained when a same-session new high
    may precede that session's low. ``max_drawdown_upper_bound`` uses only peaks known to exist
    before the current session. The unknown daily intraday order means the true drawdown lies
    between those values whenever ``intraday_drawdown_ambiguous`` is true.
    """

    event_id: str
    instrument_id: InstrumentId
    signal_index: int
    signal_date: date
    horizon: int
    status: OutcomePathStatus
    observed_sessions: int
    entry_index: int | None
    entry_date: date | None
    entry_price: float | None
    last_observed_date: date | None
    last_observed_close: float | None
    exit_date: date | None
    exit_price: float | None
    forward_return: float | None
    partial_return: float | None
    mfe: float | None
    mae: float | None
    time_to_mfe_sessions: int | None
    time_to_mae_sessions: int | None
    mfe_date: date | None
    mae_date: date | None
    extreme_order: ExtremeOrder | None
    max_drawdown_lower_bound: float | None
    max_drawdown_upper_bound: float | None
    intraday_drawdown_ambiguous: bool
    entry_gap_return: float | None
    max_gap_up_return: float | None
    max_gap_up_date: date | None
    max_gap_down_return: float | None
    max_gap_down_date: date | None
    truncation_date: date | None
    dataset_version: str
    price_representation: PriceRepresentation
    outcome_definition_version: str = "next-open-outcome-path-v0.2"


@dataclass(frozen=True, slots=True)
class _PathMetrics:
    partial_return: float
    mfe: float
    mae: float
    time_to_mfe_sessions: int
    time_to_mae_sessions: int
    mfe_date: date
    mae_date: date
    extreme_order: ExtremeOrder
    max_drawdown_lower_bound: float
    max_drawdown_upper_bound: float
    intraday_drawdown_ambiguous: bool
    entry_gap_return: float
    max_gap_up_return: float
    max_gap_up_date: date | None
    max_gap_down_return: float
    max_gap_down_date: date | None


def measure_outcome_paths(
    bars: tuple[ResearchBar, ...],
    events: tuple[EventRecord, ...],
    *,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
) -> tuple[OutcomePath, ...]:
    """Measure one explicit path record for every event/horizon combination.

    Incomplete horizons are retained with a non-``COMPLETE`` status rather than disappearing from
    the sample. Usable partial history still contributes path-only metrics, but ``forward_return``
    remains ``None`` until the requested horizon is actually complete.
    """

    _validate_inputs(bars, horizons)
    outcomes: list[OutcomePath] = []
    for event in events:
        _validate_event(bars, event)
        for horizon in horizons:
            outcomes.append(_measure_event_horizon(bars, event, horizon))
    return tuple(outcomes)


def _measure_event_horizon(
    bars: tuple[ResearchBar, ...],
    event: EventRecord,
    horizon: int,
) -> OutcomePath:
    signal = bars[event.signal_index]
    entry_index = event.signal_index + 1
    common = {
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "signal_index": event.signal_index,
        "signal_date": event.signal_date,
        "horizon": horizon,
        "dataset_version": event.dataset_version,
        "price_representation": signal.price_representation,
    }

    if entry_index >= len(bars):
        return OutcomePath(
            **common,
            status=OutcomePathStatus.NO_ENTRY_BAR,
            observed_sessions=0,
            entry_index=None,
            entry_date=None,
            entry_price=None,
            last_observed_date=None,
            last_observed_close=None,
            exit_date=None,
            exit_price=None,
            forward_return=None,
            partial_return=None,
            mfe=None,
            mae=None,
            time_to_mfe_sessions=None,
            time_to_mae_sessions=None,
            mfe_date=None,
            mae_date=None,
            extreme_order=None,
            max_drawdown_lower_bound=None,
            max_drawdown_upper_bound=None,
            intraday_drawdown_ambiguous=False,
            entry_gap_return=None,
            max_gap_up_return=None,
            max_gap_up_date=None,
            max_gap_down_return=None,
            max_gap_down_date=None,
            truncation_date=None,
        )

    entry = bars[entry_index]
    if not _usable(entry):
        return OutcomePath(
            **common,
            status=OutcomePathStatus.ENTRY_UNUSABLE,
            observed_sessions=0,
            entry_index=entry_index,
            entry_date=entry.trade_date,
            entry_price=None,
            last_observed_date=None,
            last_observed_close=None,
            exit_date=None,
            exit_price=None,
            forward_return=None,
            partial_return=None,
            mfe=None,
            mae=None,
            time_to_mfe_sessions=None,
            time_to_mae_sessions=None,
            mfe_date=None,
            mae_date=None,
            extreme_order=None,
            max_drawdown_lower_bound=None,
            max_drawdown_upper_bound=None,
            intraday_drawdown_ambiguous=False,
            entry_gap_return=None,
            max_gap_up_return=None,
            max_gap_up_date=None,
            max_gap_down_return=None,
            max_gap_down_date=None,
            truncation_date=entry.trade_date,
        )

    requested_end = entry_index + horizon
    available_end = min(requested_end, len(bars))
    candidate = bars[entry_index:available_end]
    usable_count = len(candidate)
    truncation_date: date | None = None
    status = OutcomePathStatus.COMPLETE

    for offset, bar in enumerate(candidate):
        if _usable(bar):
            continue
        usable_count = offset
        truncation_date = bar.trade_date
        status = OutcomePathStatus.TRUNCATED_UNUSABLE_BAR
        break

    if status is OutcomePathStatus.COMPLETE and len(candidate) < horizon:
        status = OutcomePathStatus.TRUNCATED_END_OF_DATA

    path = candidate[:usable_count]
    if not path:
        raise RuntimeError("usable entry bar unexpectedly produced an empty outcome path")

    metrics = _measure_metrics(
        bars,
        signal_index=event.signal_index,
        entry_index=entry_index,
        path=path,
    )
    complete = status is OutcomePathStatus.COMPLETE
    exit_bar = path[-1] if complete else None
    return OutcomePath(
        **common,
        status=status,
        observed_sessions=len(path),
        entry_index=entry_index,
        entry_date=entry.trade_date,
        entry_price=entry.open,
        last_observed_date=path[-1].trade_date,
        last_observed_close=path[-1].close,
        exit_date=exit_bar.trade_date if exit_bar is not None else None,
        exit_price=exit_bar.close if exit_bar is not None else None,
        forward_return=metrics.partial_return if complete else None,
        partial_return=metrics.partial_return,
        mfe=metrics.mfe,
        mae=metrics.mae,
        time_to_mfe_sessions=metrics.time_to_mfe_sessions,
        time_to_mae_sessions=metrics.time_to_mae_sessions,
        mfe_date=metrics.mfe_date,
        mae_date=metrics.mae_date,
        extreme_order=metrics.extreme_order,
        max_drawdown_lower_bound=metrics.max_drawdown_lower_bound,
        max_drawdown_upper_bound=metrics.max_drawdown_upper_bound,
        intraday_drawdown_ambiguous=metrics.intraday_drawdown_ambiguous,
        entry_gap_return=metrics.entry_gap_return,
        max_gap_up_return=metrics.max_gap_up_return,
        max_gap_up_date=metrics.max_gap_up_date,
        max_gap_down_return=metrics.max_gap_down_return,
        max_gap_down_date=metrics.max_gap_down_date,
        truncation_date=truncation_date,
    )


def _measure_metrics(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    entry_index: int,
    path: tuple[ResearchBar, ...],
) -> _PathMetrics:
    entry_price = path[0].open
    mfe_offset = max(range(len(path)), key=lambda index: path[index].high)
    mae_offset = min(range(len(path)), key=lambda index: path[index].low)
    mfe = path[mfe_offset].high / entry_price - 1.0
    mae = path[mae_offset].low / entry_price - 1.0

    if mfe_offset < mae_offset:
        extreme_order = ExtremeOrder.MFE_BEFORE_MAE
    elif mae_offset < mfe_offset:
        extreme_order = ExtremeOrder.MAE_BEFORE_MFE
    else:
        extreme_order = ExtremeOrder.SAME_BAR_AMBIGUOUS

    lower_drawdown, upper_drawdown = _drawdown_bounds(path, entry_price)
    gaps = tuple(
        (
            bar.open / bars[entry_index + offset - 1].close - 1.0,
            bar.trade_date,
        )
        for offset, bar in enumerate(path)
    )
    positive_gaps = tuple(item for item in gaps if item[0] > 0)
    negative_gaps = tuple(item for item in gaps if item[0] < 0)
    max_gap_up = max(positive_gaps, key=lambda item: item[0]) if positive_gaps else None
    max_gap_down = min(negative_gaps, key=lambda item: item[0]) if negative_gaps else None
    entry_gap_return = bars[entry_index].open / bars[signal_index].close - 1.0

    return _PathMetrics(
        partial_return=path[-1].close / entry_price - 1.0,
        mfe=mfe,
        mae=mae,
        time_to_mfe_sessions=mfe_offset,
        time_to_mae_sessions=mae_offset,
        mfe_date=path[mfe_offset].trade_date,
        mae_date=path[mae_offset].trade_date,
        extreme_order=extreme_order,
        max_drawdown_lower_bound=lower_drawdown,
        max_drawdown_upper_bound=upper_drawdown,
        intraday_drawdown_ambiguous=abs(lower_drawdown - upper_drawdown) > 1e-15,
        entry_gap_return=entry_gap_return,
        max_gap_up_return=max_gap_up[0] if max_gap_up is not None else 0.0,
        max_gap_up_date=max_gap_up[1] if max_gap_up is not None else None,
        max_gap_down_return=max_gap_down[0] if max_gap_down is not None else 0.0,
        max_gap_down_date=max_gap_down[1] if max_gap_down is not None else None,
    )


def _drawdown_bounds(path: tuple[ResearchBar, ...], entry_price: float) -> tuple[float, float]:
    prior_peak = entry_price
    lower_bound = 0.0
    upper_bound = 0.0
    for bar in path:
        upper_bound = min(upper_bound, bar.low / prior_peak - 1.0)
        possible_same_bar_peak = max(prior_peak, bar.high)
        lower_bound = min(lower_bound, bar.low / possible_same_bar_peak - 1.0)
        prior_peak = possible_same_bar_peak
    return lower_bound, upper_bound


def _validate_event(bars: tuple[ResearchBar, ...], event: EventRecord) -> None:
    if event.signal_index < 0 or event.signal_index >= len(bars):
        raise ValueError("event signal_index is outside the supplied research bars")
    signal = bars[event.signal_index]
    if signal.trade_date != event.signal_date:
        raise ValueError("event signal_date does not match the supplied signal bar")
    if signal.instrument_id != event.instrument_id:
        raise ValueError("event and supplied bars must reference the same instrument")
    if str(signal.dataset_version) != event.dataset_version:
        raise ValueError("event and supplied bars must reference the same dataset version")
    if not _usable(signal):
        raise ValueError("event signal bar must be eligible and quality PASS")


def _validate_inputs(bars: tuple[ResearchBar, ...], horizons: tuple[int, ...]) -> None:
    if not bars:
        raise ValueError("at least one research bar is required")
    if not horizons or any(horizon < 1 for horizon in horizons):
        raise ValueError("horizons must contain positive session counts")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must not contain duplicates")

    instruments = {bar.instrument_id for bar in bars}
    dataset_versions = {str(bar.dataset_version) for bar in bars}
    representations = {bar.price_representation for bar in bars}
    if len(instruments) != 1:
        raise ValueError("outcome measurement requires one instrument")
    if len(dataset_versions) != 1:
        raise ValueError("outcome measurement requires one dataset version")
    if len(representations) != 1:
        raise ValueError("outcome measurement cannot mix price representations")

    dates = [bar.trade_date for bar in bars]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("outcome bars must be unique and date-increasing")
    for bar in bars:
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            raise ValueError("outcome prices must be positive")
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            raise ValueError("outcome OHLC envelope is internally inconsistent")
        if bar.low > bar.high:
            raise ValueError("outcome low cannot exceed high")


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS
