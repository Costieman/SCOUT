"""Forward-path outcomes for non-event trend baseline observations.

Experiment A measures ordinary trend continuation before any consolidation/event definition is
introduced. These records therefore remain distinct from EventRecord-derived outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from trade_scout.data.contracts import InstrumentId, QualityStatus, ResearchBar


@dataclass(frozen=True, slots=True)
class TrendBaselineOutcome:
    """One trend-context signal/horizon path under next-session-open entry."""

    instrument_id: InstrumentId
    signal_index: int
    signal_date: str
    horizon: int
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    forward_return: float
    mfe: float
    mae: float
    max_drawdown: float
    dataset_version: str
    outcome_definition_version: str = "trend-next-open-forward-path-v0.1"


@dataclass(frozen=True, slots=True)
class TrendBaselineSummary:
    """Descriptive distribution summary for one trend context and horizon."""

    horizon: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None
    median_mfe: float | None
    median_mae: float | None
    median_max_drawdown: float | None


def measure_trend_baseline_outcomes(
    bars: tuple[ResearchBar, ...],
    signal_indices: tuple[int, ...],
    *,
    horizons: tuple[int, ...],
    stride: int,
) -> tuple[TrendBaselineOutcome, ...]:
    """Measure complete point-in-time trend observations at a fixed anti-clustering stride."""

    _validate_inputs(bars, horizons, stride)
    selected = _sample_indices(bars, signal_indices, stride)
    outcomes: list[TrendBaselineOutcome] = []
    for signal_index in selected:
        entry_index = signal_index + 1
        if entry_index >= len(bars):
            continue
        entry = bars[entry_index]
        if not _usable(entry):
            continue
        for horizon in horizons:
            exit_index = entry_index + horizon - 1
            if exit_index >= len(bars):
                continue
            path = bars[entry_index : exit_index + 1]
            if any(not _usable(item) for item in path):
                continue
            entry_price = entry.open
            exit_price = path[-1].close
            outcomes.append(
                TrendBaselineOutcome(
                    instrument_id=entry.instrument_id,
                    signal_index=signal_index,
                    signal_date=bars[signal_index].trade_date.isoformat(),
                    horizon=horizon,
                    entry_date=entry.trade_date.isoformat(),
                    entry_price=entry_price,
                    exit_date=path[-1].trade_date.isoformat(),
                    exit_price=exit_price,
                    forward_return=exit_price / entry_price - 1.0,
                    mfe=max(item.high / entry_price - 1.0 for item in path),
                    mae=min(item.low / entry_price - 1.0 for item in path),
                    max_drawdown=_max_drawdown(path, entry_price),
                    dataset_version=str(entry.dataset_version),
                )
            )
    return tuple(outcomes)


def summarize_trend_baseline(
    outcomes: tuple[TrendBaselineOutcome, ...],
    horizons: tuple[int, ...],
) -> tuple[TrendBaselineSummary, ...]:
    """Summarize probability, expectancy and path-risk metrics without inferential claims."""

    summaries: list[TrendBaselineSummary] = []
    for horizon in horizons:
        selected = tuple(item for item in outcomes if item.horizon == horizon)
        if not selected:
            summaries.append(
                TrendBaselineSummary(horizon, 0, None, None, None, None, None, None)
            )
            continue
        returns = tuple(item.forward_return for item in selected)
        summaries.append(
            TrendBaselineSummary(
                horizon=horizon,
                sample_size=len(selected),
                mean_return=sum(returns) / len(returns),
                median_return=median(returns),
                positive_fraction=sum(value > 0.0 for value in returns) / len(returns),
                median_mfe=median(item.mfe for item in selected),
                median_mae=median(item.mae for item in selected),
                median_max_drawdown=median(item.max_drawdown for item in selected),
            )
        )
    return tuple(summaries)


def _sample_indices(
    bars: tuple[ResearchBar, ...], signal_indices: tuple[int, ...], stride: int
) -> tuple[int, ...]:
    selected: list[int] = []
    last = -10_000
    for index in signal_indices:
        if index < 0 or index >= len(bars):
            raise ValueError(f"signal index outside bar range: {index}")
        if index - last < stride:
            continue
        if not _usable(bars[index]):
            continue
        selected.append(index)
        last = index
    return tuple(selected)


def _max_drawdown(path: tuple[ResearchBar, ...], entry_price: float) -> float:
    peak = entry_price
    worst = 0.0
    for bar in path:
        peak = max(peak, bar.high)
        worst = min(worst, bar.low / peak - 1.0)
    return worst


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _validate_inputs(
    bars: tuple[ResearchBar, ...], horizons: tuple[int, ...], stride: int
) -> None:
    if not bars:
        raise ValueError("trend baseline requires at least one research bar")
    if not horizons or any(horizon < 1 for horizon in horizons):
        raise ValueError("trend baseline horizons must be positive")
    if len(set(horizons)) != len(horizons):
        raise ValueError("trend baseline horizons must not contain duplicates")
    if stride < 1:
        raise ValueError("trend baseline stride must be positive")
