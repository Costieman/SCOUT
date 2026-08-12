"""Point-in-time historical signal generation for immutable strategy definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.app.feature_expression import compile_feature_expression
from trade_scout.app.strategy_definition import StrategyDefinition
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.market_analysis import (
    MARKET_ANALYSIS_FEATURE_SET,
    compute_market_analysis_feature_frame,
)

_EXPRESSION_NAMES = frozenset(item.feature_name for item in MARKET_ANALYSIS_FEATURE_SET.definitions)


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """One selected instrument/session from a historical cross-sectional strategy evaluation."""

    strategy_id: str
    instrument_id: InstrumentId
    trade_date: date
    rank_feature: str
    rank_value: float
    dataset_version: DatasetVersion
    feature_set_version: str


def evaluate_strategy_signal_history(
    bars: tuple[DailyBar, ...],
    strategy: StrategyDefinition,
) -> tuple[StrategySignal, ...]:
    """Evaluate a strategy independently at every session using only point-in-time features.

    Qualifying instruments are ranked cross-sectionally on each date and truncated to the
    strategy's declared limit. No forward prices, outcomes, or execution assumptions participate
    in signal formation.
    """

    frame = compute_market_analysis_feature_frame(bars)
    expression = compile_feature_expression(strategy.expression, allowed_names=_EXPRESSION_NAMES)

    by_instrument_date: dict[tuple[InstrumentId, date], dict[str, float | None]] = {}
    metadata: dict[tuple[InstrumentId, date], tuple[DatasetVersion, str]] = {}
    for item in frame:
        key = (item.instrument_id, item.trade_date)
        values = by_instrument_date.setdefault(key, {})
        values[item.feature_name] = (
            item.value if item.availability_status is FeatureAvailabilityStatus.AVAILABLE else None
        )
        metadata[key] = (item.dataset_version, item.feature_set_version)

    candidates_by_date: dict[date, list[StrategySignal]] = {}
    for (instrument_id, trade_date), values in by_instrument_date.items():
        if not expression.evaluate(values):
            continue
        rank_value = values.get(strategy.sort_by)
        if rank_value is None:
            continue
        dataset_version, feature_set_version = metadata[(instrument_id, trade_date)]
        candidates_by_date.setdefault(trade_date, []).append(
            StrategySignal(
                strategy_id=strategy.strategy_id,
                instrument_id=instrument_id,
                trade_date=trade_date,
                rank_feature=strategy.sort_by,
                rank_value=rank_value,
                dataset_version=dataset_version,
                feature_set_version=feature_set_version,
            )
        )

    selected: list[StrategySignal] = []
    for trade_date in sorted(candidates_by_date):
        daily = candidates_by_date[trade_date]
        daily.sort(
            key=lambda item: (item.rank_value, str(item.instrument_id)),
            reverse=strategy.descending,
        )
        selected.extend(daily[: strategy.limit])
    return tuple(selected)


__all__ = ["StrategySignal", "evaluate_strategy_signal_history"]
