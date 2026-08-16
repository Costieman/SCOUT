"""Forward-path measurements for exploratory event research.

The engine keeps entry semantics explicit: close-confirmed signals enter at the next
session open. It measures outcomes after an already-defined event and never changes
whether that event existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from trade_scout.data.contracts import InstrumentId, QualityStatus, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.outcomes.path import OutcomePathStatus, measure_outcome_paths


@dataclass(frozen=True, slots=True)
class ForwardOutcome:
    """One complete event/horizon outcome under next-session-open entry."""

    event_id: str
    instrument_id: InstrumentId
    horizon: int
    entry_index: int
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    forward_return: float
    mfe: float
    mae: float
    max_drawdown: float
    dataset_version: str
    outcome_definition_version: str = "next-open-forward-path-v0.1"


@dataclass(frozen=True, slots=True)
class HorizonSummary:
    """Aggregate exploratory distribution at one fixed horizon."""

    horizon: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None
    return_p25: float | None
    return_p75: float | None
    median_mfe: float | None
    median_mae: float | None


def measure_forward_outcomes(
    bars: tuple[ResearchBar, ...],
    events: tuple[EventRecord, ...],
    *,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
) -> tuple[ForwardOutcome, ...]:
    """Measure complete event/horizon paths using the canonical outcome-path engine.

    This compatibility surface retains the original behavior in which incomplete horizons are
    absent. New research requiring explicit truncation, gaps, timing, or daily-bar ambiguity
    should consume :func:`trade_scout.outcomes.path.measure_outcome_paths` directly.
    """

    paths = measure_outcome_paths(bars, events, horizons=horizons)
    outcomes: list[ForwardOutcome] = []
    for path in paths:
        if path.status is not OutcomePathStatus.COMPLETE:
            continue
        if (
            path.entry_index is None
            or path.entry_date is None
            or path.entry_price is None
            or path.exit_date is None
            or path.exit_price is None
            or path.forward_return is None
            or path.mfe is None
            or path.mae is None
            or path.max_drawdown_lower_bound is None
        ):
            raise RuntimeError("complete outcome path is missing required complete-path metrics")
        outcomes.append(
            ForwardOutcome(
                event_id=path.event_id,
                instrument_id=path.instrument_id,
                horizon=path.horizon,
                entry_index=path.entry_index,
                entry_date=path.entry_date.isoformat(),
                entry_price=path.entry_price,
                exit_date=path.exit_date.isoformat(),
                exit_price=path.exit_price,
                forward_return=path.forward_return,
                mfe=path.mfe,
                mae=path.mae,
                max_drawdown=path.max_drawdown_lower_bound,
                dataset_version=path.dataset_version,
            )
        )
    return tuple(outcomes)


def measure_baseline_outcomes(
    bars: tuple[ResearchBar, ...],
    signal_indices: tuple[int, ...],
    *,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
    stride: int = 5,
) -> dict[int, tuple[float, ...]]:
    """Measure a simple non-event context baseline from point-in-time signal dates.

    The baseline is intentionally modest: eligible signal dates satisfying the same trend
    context are sampled at a fixed stride, then entered at next-session open. It is not a
    matched or statistically independent comparator and must be labelled accordingly.
    """

    _validate_inputs(bars, horizons)
    if stride < 1:
        raise ValueError("stride must be positive")
    selected: list[int] = []
    last = -10_000
    for index in signal_indices:
        if index - last < stride:
            continue
        if index + 1 >= len(bars):
            continue
        if not _usable(bars[index]) or not _usable(bars[index + 1]):
            continue
        selected.append(index)
        last = index

    values: dict[int, list[float]] = {horizon: [] for horizon in horizons}
    for signal_index in selected:
        entry_index = signal_index + 1
        entry_price = bars[entry_index].open
        for horizon in horizons:
            exit_index = entry_index + horizon - 1
            if exit_index >= len(bars):
                continue
            path = bars[entry_index : exit_index + 1]
            if any(not _usable(item) for item in path):
                continue
            values[horizon].append(path[-1].close / entry_price - 1.0)
    return {key: tuple(items) for key, items in values.items()}


def summarize_outcomes(
    outcomes: tuple[ForwardOutcome, ...],
    horizons: tuple[int, ...],
) -> tuple[HorizonSummary, ...]:
    """Summarize event-level distributions without inferential claims."""

    summaries: list[HorizonSummary] = []
    for horizon in horizons:
        selected = tuple(item for item in outcomes if item.horizon == horizon)
        returns = tuple(item.forward_return for item in selected)
        if not returns:
            summaries.append(
                HorizonSummary(
                    horizon=horizon,
                    sample_size=0,
                    mean_return=None,
                    median_return=None,
                    positive_fraction=None,
                    return_p25=None,
                    return_p75=None,
                    median_mfe=None,
                    median_mae=None,
                )
            )
            continue
        ordered = tuple(sorted(returns))
        summaries.append(
            HorizonSummary(
                horizon=horizon,
                sample_size=len(returns),
                mean_return=sum(returns) / len(returns),
                median_return=median(returns),
                positive_fraction=sum(value > 0 for value in returns) / len(returns),
                return_p25=_quantile(ordered, 0.25),
                return_p75=_quantile(ordered, 0.75),
                median_mfe=median(item.mfe for item in selected),
                median_mae=median(item.mae for item in selected),
            )
        )
    return tuple(summaries)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if len(values) == 1:
        return values[0]
    position = probability * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _validate_inputs(bars: tuple[ResearchBar, ...], horizons: tuple[int, ...]) -> None:
    if not bars:
        raise ValueError("at least one research bar is required")
    if not horizons or any(item < 1 for item in horizons):
        raise ValueError("horizons must contain positive session counts")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must not contain duplicates")
