"""Forward outcome measurement for point-in-time strategy signals."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from trade_scout.app.strategy_signal_history import StrategySignal
from trade_scout.data.contracts import DailyBar, InstrumentId, QualityStatus


@dataclass(frozen=True, slots=True)
class StrategyForwardOutcome:
    """One signal/horizon outcome under next-session split-adjusted-open entry."""

    strategy_id: str
    instrument_id: InstrumentId
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
    outcome_definition_version: str = "strategy-next-open-split-adjusted-v0.1"


@dataclass(frozen=True, slots=True)
class StrategyHorizonSummary:
    horizon: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None
    median_mfe: float | None
    median_mae: float | None
    median_max_drawdown: float | None


def measure_strategy_forward_outcomes(
    bars: tuple[DailyBar, ...],
    signals: tuple[StrategySignal, ...],
    *,
    horizons: tuple[int, ...] = (5, 20, 60),
) -> tuple[StrategyForwardOutcome, ...]:
    """Measure complete forward paths without changing signal selection."""

    if not horizons or any(item < 1 for item in horizons):
        raise ValueError("horizons must contain positive session counts")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must not contain duplicates")

    by_instrument: dict[InstrumentId, tuple[DailyBar, ...]] = {}
    instrument_rows: dict[InstrumentId, list[DailyBar]] = {}
    for bar in bars:
        if bar.quality_status is not QualityStatus.PASS:
            raise ValueError("strategy outcomes require PASS canonical bars")
        instrument_rows.setdefault(bar.instrument_id, []).append(bar)
    for instrument_id, rows in instrument_rows.items():
        by_instrument[instrument_id] = tuple(sorted(rows, key=lambda item: item.trade_date))

    outcomes: list[StrategyForwardOutcome] = []
    for signal in signals:
        series = by_instrument.get(signal.instrument_id)
        if not series:
            continue
        signal_index = next(
            (index for index, bar in enumerate(series) if bar.trade_date == signal.trade_date),
            None,
        )
        if signal_index is None or signal_index + 1 >= len(series):
            continue
        entry_index = signal_index + 1
        entry = series[entry_index]
        entry_price = entry.open_split_adjusted
        if entry_price is None or entry_price <= 0:
            continue
        for horizon in horizons:
            exit_index = entry_index + horizon - 1
            if exit_index >= len(series):
                continue
            path = series[entry_index : exit_index + 1]
            adjusted = tuple(
                (
                    item.high_split_adjusted,
                    item.low_split_adjusted,
                    item.close_split_adjusted,
                )
                for item in path
            )
            if any(
                high is None or low is None or close is None
                for high, low, close in adjusted
            ):
                continue
            highs = tuple(float(high) for high, _, _ in adjusted if high is not None)
            lows = tuple(float(low) for _, low, _ in adjusted if low is not None)
            closes = tuple(float(close) for _, _, close in adjusted if close is not None)
            exit_price = closes[-1]
            outcomes.append(
                StrategyForwardOutcome(
                    strategy_id=signal.strategy_id,
                    instrument_id=signal.instrument_id,
                    signal_date=signal.trade_date.isoformat(),
                    horizon=horizon,
                    entry_date=entry.trade_date.isoformat(),
                    entry_price=entry_price,
                    exit_date=path[-1].trade_date.isoformat(),
                    exit_price=exit_price,
                    forward_return=exit_price / entry_price - 1.0,
                    mfe=max(value / entry_price - 1.0 for value in highs),
                    mae=min(value / entry_price - 1.0 for value in lows),
                    max_drawdown=_max_drawdown(highs, lows, entry_price),
                    dataset_version=str(entry.dataset_version),
                )
            )
    return tuple(outcomes)


def summarize_strategy_outcomes(
    outcomes: tuple[StrategyForwardOutcome, ...],
    horizons: tuple[int, ...],
) -> tuple[StrategyHorizonSummary, ...]:
    """Return descriptive horizon summaries without inferential or trading claims."""

    summaries: list[StrategyHorizonSummary] = []
    for horizon in horizons:
        selected = tuple(item for item in outcomes if item.horizon == horizon)
        if not selected:
            summaries.append(
                StrategyHorizonSummary(
                    horizon=horizon,
                    sample_size=0,
                    mean_return=None,
                    median_return=None,
                    positive_fraction=None,
                    median_mfe=None,
                    median_mae=None,
                    median_max_drawdown=None,
                )
            )
            continue
        returns = tuple(item.forward_return for item in selected)
        summaries.append(
            StrategyHorizonSummary(
                horizon=horizon,
                sample_size=len(selected),
                mean_return=sum(returns) / len(returns),
                median_return=median(returns),
                positive_fraction=sum(value > 0 for value in returns) / len(returns),
                median_mfe=median(item.mfe for item in selected),
                median_mae=median(item.mae for item in selected),
                median_max_drawdown=median(item.max_drawdown for item in selected),
            )
        )
    return tuple(summaries)


def _max_drawdown(highs: tuple[float, ...], lows: tuple[float, ...], entry_price: float) -> float:
    peak = entry_price
    worst = 0.0
    for high, low in zip(highs, lows, strict=True):
        peak = max(peak, high)
        worst = min(worst, low / peak - 1.0)
    return worst


__all__ = [
    "StrategyForwardOutcome",
    "StrategyHorizonSummary",
    "measure_strategy_forward_outcomes",
    "summarize_strategy_outcomes",
]
