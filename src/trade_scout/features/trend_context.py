"""Point-in-time trend-context definitions for the first research program.

The specification defines T0-T6 semantically but does not fix the lookback used to judge a rising
200-day average or the trailing-return/relative-strength interval. Those choices therefore remain
explicit configuration rather than hidden defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.data.contracts import QualityStatus, ResearchBar


class TrendContext(StrEnum):
    """Candidate trend definitions registered by the consolidation-breakout research program."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"


@dataclass(frozen=True, slots=True)
class TrendContextConfig:
    """Resolved numerical choices required to make the semantic T0-T6 rules executable."""

    sma_200_period: int = 200
    sma_50_period: int = 50
    sma_slope_lookback: int = 20
    trailing_return_intervals: int = 60
    relative_strength_intervals: int = 60

    def __post_init__(self) -> None:
        values = (
            self.sma_200_period,
            self.sma_50_period,
            self.sma_slope_lookback,
            self.trailing_return_intervals,
            self.relative_strength_intervals,
        )
        if any(value < 1 for value in values):
            raise ValueError("trend-context lookbacks must be positive")


def qualifying_trend_indices(
    bars: tuple[ResearchBar, ...],
    *,
    context: TrendContext,
    config: TrendContextConfig,
    benchmark_bars: tuple[ResearchBar, ...] | None = None,
) -> tuple[int, ...]:
    """Return signal indices satisfying one trend rule using information available through t."""

    _validate_bars(bars)
    benchmark_by_date = _benchmark_closes(benchmark_bars) if benchmark_bars is not None else None
    if context is TrendContext.T6 and benchmark_by_date is None:
        raise ValueError("T6 requires an explicit benchmark series")

    closes = tuple(bar.close for bar in bars)
    eligible: list[int] = []
    for index, bar in enumerate(bars):
        if not _usable(bar):
            continue
        if _qualifies(
            closes,
            bars,
            index,
            context=context,
            config=config,
            benchmark_by_date=benchmark_by_date,
        ):
            eligible.append(index)
    return tuple(eligible)


def _qualifies(
    closes: tuple[float, ...],
    bars: tuple[ResearchBar, ...],
    index: int,
    *,
    context: TrendContext,
    config: TrendContextConfig,
    benchmark_by_date: dict[object, float] | None,
) -> bool:
    if context is TrendContext.T0:
        return True

    sma_200 = _sma(closes, index, config.sma_200_period)
    if sma_200 is None or closes[index] <= sma_200:
        return False
    if context is TrendContext.T1:
        return True

    if context in {TrendContext.T2, TrendContext.T5, TrendContext.T6}:
        prior_index = index - config.sma_slope_lookback
        prior_sma_200 = _sma(closes, prior_index, config.sma_200_period)
        if prior_sma_200 is None or sma_200 <= prior_sma_200:
            return False
    if context is TrendContext.T2:
        return True

    if context in {TrendContext.T3, TrendContext.T4}:
        sma_50 = _sma(closes, index, config.sma_50_period)
        if sma_50 is None or closes[index] <= sma_50:
            return False
        if context is TrendContext.T3:
            return True
        return sma_50 > sma_200

    if context is TrendContext.T5:
        trailing = _return(closes, index, config.trailing_return_intervals)
        return trailing is not None and trailing > 0.0

    if context is TrendContext.T6:
        stock_return = _return(closes, index, config.relative_strength_intervals)
        benchmark_return = _benchmark_return(
            bars,
            index,
            config.relative_strength_intervals,
            benchmark_by_date or {},
        )
        return (
            stock_return is not None
            and benchmark_return is not None
            and stock_return > benchmark_return
        )

    raise AssertionError(f"unsupported trend context: {context}")


def _sma(values: tuple[float, ...], index: int, period: int) -> float | None:
    start = index - period + 1
    if start < 0 or index < 0:
        return None
    window = values[start : index + 1]
    return sum(window) / period


def _return(values: tuple[float, ...], index: int, intervals: int) -> float | None:
    prior = index - intervals
    if prior < 0 or values[prior] <= 0:
        return None
    return values[index] / values[prior] - 1.0


def _benchmark_return(
    bars: tuple[ResearchBar, ...],
    index: int,
    intervals: int,
    benchmark_by_date: dict[object, float],
) -> float | None:
    prior = index - intervals
    if prior < 0:
        return None
    current_close = benchmark_by_date.get(bars[index].trade_date)
    prior_close = benchmark_by_date.get(bars[prior].trade_date)
    if current_close is None or prior_close is None or prior_close <= 0:
        return None
    return current_close / prior_close - 1.0


def _benchmark_closes(bars: tuple[ResearchBar, ...]) -> dict[object, float]:
    _validate_bars(bars)
    return {bar.trade_date: bar.close for bar in bars if _usable(bar)}


def _validate_bars(bars: tuple[ResearchBar, ...]) -> None:
    if not bars:
        raise ValueError("trend-context evaluation requires at least one research bar")
    instrument_ids = {str(bar.instrument_id) for bar in bars}
    dataset_versions = {str(bar.dataset_version) for bar in bars}
    if len(instrument_ids) != 1:
        raise ValueError("trend-context evaluation accepts one instrument at a time")
    if len(dataset_versions) != 1:
        raise ValueError("trend-context evaluation cannot mix dataset versions")
    dates = tuple(bar.trade_date for bar in bars)
    if dates != tuple(sorted(dates)) or len(set(dates)) != len(dates):
        raise ValueError("trend-context bars must be unique and ordered by trade date")


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS
