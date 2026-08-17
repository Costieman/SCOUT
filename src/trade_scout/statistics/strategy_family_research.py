"""Batch signal selection for a predeclared family of related feature strategies.

This module exists for controlled one-variable entry-parameter sweeps. It materializes the shared
fixed feature frame once, joins a precomputed union of parameterized features, and then evaluates
multiple safe expressions without changing the point-in-time signal semantics used by the normal
single-strategy research runner.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from datetime import date

from trade_scout.data.contracts import DailyBar, InstrumentId, QualityStatus
from trade_scout.features.contracts import (
    FeatureAvailabilityStatus,
    FeatureSetDefinition,
    FeatureValue,
)
from trade_scout.features.expression import compile_feature_expression
from trade_scout.features.market_analysis import (
    MARKET_ANALYSIS_FEATURE_SET,
    MARKET_ANALYSIS_FEATURE_SET_VERSION,
    compute_market_analysis_feature_frame,
)
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    StrategyResearchReport,
    StrategySignal,
    available_strategy_features,
)


def run_feature_strategy_signal_family(
    bars: Iterable[DailyBar],
    *,
    strategies: tuple[StrategyDefinition, ...],
    signal_start: date | None = None,
    signal_end: date | None = None,
    extra_features: Iterable[FeatureValue] = (),
) -> tuple[StrategyResearchReport, ...]:
    """Select signals for related strategies while reusing common feature materialization."""

    materialized = tuple(bars)
    additional = tuple(extra_features)
    if not materialized:
        raise ValueError("strategy family research requires canonical daily bars")
    if not strategies:
        raise ValueError("strategy family research requires at least one strategy")
    if len({item.strategy_id for item in strategies}) != len(strategies):
        raise ValueError("strategy family strategy IDs must be unique")
    if signal_start is not None and signal_end is not None and signal_start > signal_end:
        raise ValueError("signal_start cannot be after signal_end")

    versions = {str(item.dataset_version) for item in materialized}
    if len(versions) != 1:
        raise ValueError("strategy family research cannot mix canonical dataset versions")
    if any(item.quality_status is not QualityStatus.PASS for item in materialized):
        raise ValueError("strategy family research requires PASS canonical bars")
    dataset_version = next(iter(versions))

    allowed_fixed = frozenset(available_strategy_features())
    extra_names = {item.feature_name for item in additional}
    collisions = sorted(extra_names & allowed_fixed)
    if collisions:
        raise ValueError(f"extra features cannot shadow registered strategy features: {collisions}")
    if additional and {str(item.dataset_version) for item in additional} != {dataset_version}:
        raise ValueError("extra strategy features must use the same canonical dataset version")
    extra_versions = sorted({item.feature_set_version for item in additional})
    feature_set_version = "+".join((MARKET_ANALYSIS_FEATURE_SET_VERSION, *extra_versions))
    allowed_names = allowed_fixed | frozenset(extra_names)
    compiled = {
        item.strategy_id: compile_feature_expression(item.expression, allowed_names=allowed_names)
        for item in strategies
    }

    required_fixed_names = set()
    for strategy in strategies:
        required_fixed_names.update(_fixed_names(strategy.expression, allowed_fixed))
        required_fixed_names.add(strategy.rank_feature)
    definitions = tuple(
        definition
        for definition in MARKET_ANALYSIS_FEATURE_SET.definitions
        if definition.feature_name in required_fixed_names
    )
    if not definitions:
        raise ValueError("strategy family requires at least one registered fixed feature")
    feature_set = FeatureSetDefinition(
        feature_set_version=MARKET_ANALYSIS_FEATURE_SET_VERSION,
        definitions=definitions,
    )

    by_instrument: dict[InstrumentId, list[DailyBar]] = {}
    for bar in materialized:
        by_instrument.setdefault(bar.instrument_id, []).append(bar)
    ordered_by_instrument = {
        instrument_id: tuple(sorted(rows, key=lambda item: item.trade_date))
        for instrument_id, rows in by_instrument.items()
    }
    for instrument_id, rows in ordered_by_instrument.items():
        dates = tuple(item.trade_date for item in rows)
        if len(dates) != len(set(dates)):
            raise ValueError(f"duplicate canonical dates for {instrument_id}")

    extra_by_instrument: dict[InstrumentId, list[FeatureValue]] = {}
    seen_extra: set[tuple[InstrumentId, date, str]] = set()
    for item in additional:
        key = (item.instrument_id, item.trade_date, item.feature_name)
        if key in seen_extra:
            raise ValueError(f"duplicate extra strategy feature observation: {key}")
        seen_extra.add(key)
        if item.instrument_id not in ordered_by_instrument:
            raise ValueError(f"extra feature references unknown instrument {item.instrument_id}")
        extra_by_instrument.setdefault(item.instrument_id, []).append(item)

    candidates: dict[str, dict[date, list[StrategySignal]]] = {
        item.strategy_id: {} for item in strategies
    }
    for instrument_id, rows in ordered_by_instrument.items():
        frame = compute_market_analysis_feature_frame(rows, feature_set=feature_set)
        values_by_date: dict[date, dict[str, float | None]] = {}
        for item in (*frame, *extra_by_instrument.get(instrument_id, ())):
            values_by_date.setdefault(item.trade_date, {})[item.feature_name] = (
                float(item.value)
                if item.availability_status is FeatureAvailabilityStatus.AVAILABLE
                and item.value is not None
                else None
            )
        index_by_date = {bar.trade_date: index for index, bar in enumerate(rows)}
        for trade_date, values in values_by_date.items():
            if trade_date not in index_by_date:
                continue
            if signal_start is not None and trade_date < signal_start:
                continue
            if signal_end is not None and trade_date > signal_end:
                continue
            for strategy in strategies:
                if not compiled[strategy.strategy_id].evaluate(values):
                    continue
                rank_value = values.get(strategy.rank_feature)
                if rank_value is None:
                    continue
                candidates[strategy.strategy_id].setdefault(trade_date, []).append(
                    StrategySignal(
                        strategy_id=strategy.strategy_id,
                        instrument_id=instrument_id,
                        signal_date=trade_date,
                        signal_index=index_by_date[trade_date],
                        rank_feature=strategy.rank_feature,
                        rank_value=rank_value,
                        dataset_version=dataset_version,
                        feature_set_version=feature_set_version,
                    )
                )

    warnings = (
        "Exploratory one-variable strategy-family research only; no child is validated by this sweep.",
        "All child expressions are evaluated point-in-time from one shared canonical working window.",
        "Outcome measurement is intentionally deferred to the shared downstream exit engine.",
    )
    reports: list[StrategyResearchReport] = []
    for strategy in strategies:
        selected: list[StrategySignal] = []
        for trade_date in sorted(candidates[strategy.strategy_id]):
            daily = candidates[strategy.strategy_id][trade_date]
            if strategy.descending:
                daily.sort(key=lambda item: (-item.rank_value, str(item.instrument_id)))
            else:
                daily.sort(key=lambda item: (item.rank_value, str(item.instrument_id)))
            selected.extend(daily[: strategy.per_session_limit])
        signals = tuple(selected)
        reports.append(
            StrategyResearchReport(
                strategy=strategy,
                dataset_version=dataset_version,
                feature_set_version=feature_set_version,
                instrument_count=len(ordered_by_instrument),
                signal_count=len(signals),
                horizons=(),
                signal_start=signal_start,
                signal_end=signal_end,
                signals=signals,
                outcomes=(),
                summaries=(),
                warnings=warnings,
            )
        )
    return tuple(reports)


def _fixed_names(expression: str, allowed: frozenset[str]) -> set[str]:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError("cannot inspect malformed strategy expression") from exc
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in allowed
    }


__all__ = ["run_feature_strategy_signal_family"]
