"""Executable Experiment A adapter for the first research program.

This module connects immutable canonical daily bars, point-in-time universe membership, registered
trend-context logic, and non-event forward-path outcomes. It performs orchestration only; the trend
and outcome calculations remain owned by their domain modules.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, cast

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    ResearchBar,
    to_research_bar,
)
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    JSONValue,
    ResearchMode,
    StageResult,
)
from trade_scout.features.trend_context import (
    TrendContext,
    TrendContextConfig,
    qualifying_trend_indices,
)
from trade_scout.outcomes.trend_baseline import (
    TrendBaselineOutcome,
    TrendBaselineSummary,
    measure_trend_baseline_outcomes,
    summarize_trend_baseline,
)
from trade_scout.universe.eligibility import UniverseMembershipRecord

TREND_BASELINE_STAGE_NAME = "trend_baseline"
TREND_CONTEXT_DEFINITION_VERSION = "first-program-trend-context-v0.1"
EXPERIMENT_A_SMA_200_PERIOD = 200
EXPERIMENT_A_SMA_50_PERIOD = 50


class EligibilityResolver(Protocol):
    """Resolve point-in-time universe eligibility for canonical instrument/date keys."""

    @property
    def universe_version(self) -> str: ...

    def is_eligible(self, instrument_id: InstrumentId, trade_date: date) -> bool: ...


class MembershipEligibilityResolver:
    """Resolve eligibility from already-computed immutable universe membership records."""

    def __init__(
        self, records: Iterable[UniverseMembershipRecord], *, universe_version: str
    ) -> None:
        materialized = tuple(records)
        if not universe_version.strip():
            raise ValueError("universe_version must be non-empty")
        if any(record.universe_version != universe_version for record in materialized):
            raise ValueError("membership records do not match the requested universe version")
        self._universe_version = universe_version
        self._membership = {
            (str(record.instrument_id), record.as_of): record.eligible for record in materialized
        }
        if len(self._membership) != len(materialized):
            raise ValueError("duplicate point-in-time universe membership keys")

    @property
    def universe_version(self) -> str:
        return self._universe_version

    def is_eligible(self, instrument_id: InstrumentId, trade_date: date) -> bool:
        """Fail closed when a historical membership decision is absent."""

        return self._membership.get((str(instrument_id), trade_date), False)


@dataclass(frozen=True, slots=True)
class TrendBaselineDataset:
    """Research-ready bars loaded from one immutable canonical dataset version."""

    by_instrument: dict[str, tuple[ResearchBar, ...]]
    benchmark_bars: tuple[ResearchBar, ...] | None


class CanonicalTrendBaselineSource:
    """Materialize split-adjusted research bars from the immutable canonical daily-bar store."""

    def __init__(
        self,
        store: CanonicalDailyBarStore,
        eligibility: EligibilityResolver,
        *,
        benchmark_instrument_id: InstrumentId | None = None,
    ) -> None:
        self._store = store
        self._eligibility = eligibility
        self._benchmark_instrument_id = benchmark_instrument_id

    @property
    def universe_version(self) -> str:
        return self._eligibility.universe_version

    def load(self, dataset_version: str) -> TrendBaselineDataset:
        """Load one verified canonical version and attach point-in-time eligibility."""

        canonical = self._store.load(DatasetVersion(dataset_version))
        grouped: dict[str, list[ResearchBar]] = {}
        benchmark: list[ResearchBar] = []
        benchmark_key = (
            None if self._benchmark_instrument_id is None else str(self._benchmark_instrument_id)
        )
        for bar in canonical:
            key = str(bar.instrument_id)
            is_benchmark = benchmark_key is not None and key == benchmark_key
            research_bar = to_research_bar(
                bar,
                representation=PriceRepresentation.SPLIT_ADJUSTED,
                eligibility=(
                    True
                    if is_benchmark
                    else self._eligibility.is_eligible(bar.instrument_id, bar.trade_date)
                ),
            )
            if is_benchmark:
                benchmark.append(research_bar)
            else:
                grouped.setdefault(key, []).append(research_bar)

        by_instrument = {
            key: tuple(sorted(values, key=lambda item: item.trade_date))
            for key, values in sorted(grouped.items())
        }
        benchmark_bars = (
            tuple(sorted(benchmark, key=lambda item: item.trade_date)) if benchmark else None
        )
        return TrendBaselineDataset(by_instrument=by_instrument, benchmark_bars=benchmark_bars)


@dataclass(frozen=True, slots=True)
class ExperimentATrendBaselineStage:
    """ResearchStage adapter executing one resolved T0-T6 Experiment A child run."""

    source: CanonicalTrendBaselineSource

    @property
    def name(self) -> str:
        return TREND_BASELINE_STAGE_NAME

    def run(self, context: ExperimentContext) -> StageResult:
        """Execute descriptive trend-baseline measurement through public domain contracts."""

        definition = context.definition
        if definition.universe_version != self.source.universe_version:
            raise ValueError("experiment universe version does not match eligibility source")
        resolved = _experiment_a_config(definition.resolved_configuration)
        trend_context = TrendContext(_string(resolved, "trend_context"))
        trend_config = TrendContextConfig(
            sma_200_period=_integer(resolved, "sma_200_period"),
            sma_50_period=_integer(resolved, "sma_50_period"),
            sma_slope_lookback=_integer(resolved, "sma_slope_lookback"),
            trailing_return_intervals=_integer(resolved, "trailing_return_intervals"),
            relative_strength_intervals=_integer(resolved, "relative_strength_intervals"),
        )
        _validate_experiment_a_periods(trend_config)
        horizons = _integer_tuple(resolved, "outcome_horizons")
        stride = _integer(resolved, "sampling_stride")

        dataset = self.source.load(definition.dataset_version)
        if trend_context is TrendContext.T6 and dataset.benchmark_bars is None:
            raise ValueError("Experiment A T6 requires benchmark bars in the canonical source")

        outcomes: list[TrendBaselineOutcome] = []
        signal_count = 0
        instruments_with_signals = 0
        for bars in dataset.by_instrument.values():
            indices = qualifying_trend_indices(
                bars,
                context=trend_context,
                config=trend_config,
                benchmark_bars=dataset.benchmark_bars,
            )
            if indices:
                instruments_with_signals += 1
                signal_count += len(indices)
            outcomes.extend(
                measure_trend_baseline_outcomes(
                    bars,
                    indices,
                    horizons=horizons,
                    stride=stride,
                )
            )

        summaries = summarize_trend_baseline(tuple(outcomes), horizons)
        return StageResult(
            stage_name=self.name,
            outputs={
                "program_experiment": "A",
                "trend_context": trend_context.value,
                "trend_context_definition_version": TREND_CONTEXT_DEFINITION_VERSION,
                "dataset_version": definition.dataset_version,
                "universe_version": definition.universe_version,
                "instrument_count": len(dataset.by_instrument),
                "instruments_with_signals": instruments_with_signals,
                "qualifying_signal_count_before_stride": signal_count,
                "measured_outcome_count": len(outcomes),
                "outcome_definition_version": "trend-next-open-forward-path-v0.1",
                "summaries": [_summary_json(item) for item in summaries],
            },
        )


def experiment_a_definition(
    *,
    trend_context: TrendContext,
    dataset_version: str,
    universe_version: str,
    code_version: str,
    config_schema_version: str,
    outcome_horizons: tuple[int, ...],
    sampling_stride: int,
    sma_slope_lookback: int,
    trailing_return_intervals: int,
    relative_strength_intervals: int,
) -> ExperimentDefinition:
    """Build one fully resolved exploratory Experiment A child definition."""

    config = TrendContextConfig(
        sma_200_period=EXPERIMENT_A_SMA_200_PERIOD,
        sma_50_period=EXPERIMENT_A_SMA_50_PERIOD,
        sma_slope_lookback=sma_slope_lookback,
        trailing_return_intervals=trailing_return_intervals,
        relative_strength_intervals=relative_strength_intervals,
    )
    if not outcome_horizons or any(value < 1 for value in outcome_horizons):
        raise ValueError("Experiment A outcome horizons must be positive")
    if sampling_stride < 1:
        raise ValueError("Experiment A sampling stride must be positive")

    return ExperimentDefinition(
        name=f"first_program_A_trend_baseline_{trend_context.value}",
        hypothesis=(
            "Ordinary forward return and path-risk distributions differ across registered trend "
            "contexts before consolidation structure is introduced."
        ),
        mode=ResearchMode.EXPLORATORY,
        dataset_version=dataset_version,
        universe_version=universe_version,
        code_version=code_version,
        config_schema_version=config_schema_version,
        hypothesis_family_id="first-program-A-trend-baseline",
        resolved_configuration={
            "experiment_a": {
                "trend_context": trend_context.value,
                "trend_context_definition_version": TREND_CONTEXT_DEFINITION_VERSION,
                "outcome_horizons": list(outcome_horizons),
                "sampling_stride": sampling_stride,
                "sma_200_period": config.sma_200_period,
                "sma_50_period": config.sma_50_period,
                "sma_slope_lookback": config.sma_slope_lookback,
                "trailing_return_intervals": config.trailing_return_intervals,
                "relative_strength_intervals": config.relative_strength_intervals,
                "price_representation": PriceRepresentation.SPLIT_ADJUSTED.value,
                "entry_convention": "next_session_open",
            }
        },
    )


def _validate_experiment_a_periods(config: TrendContextConfig) -> None:
    if config.sma_200_period != EXPERIMENT_A_SMA_200_PERIOD:
        raise ValueError("Experiment A T1/T2/T3/T4/T5/T6 requires a 200-session SMA")
    if config.sma_50_period != EXPERIMENT_A_SMA_50_PERIOD:
        raise ValueError("Experiment A T3/T4 requires a 50-session SMA")


def _experiment_a_config(configuration: dict[str, JSONValue]) -> dict[str, JSONValue]:
    raw = configuration.get("experiment_a")
    if not isinstance(raw, dict):
        raise ValueError("resolved configuration must contain an experiment_a mapping")
    return raw


def _string(values: dict[str, JSONValue], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Experiment A config field {key} must be a non-empty string")
    return value


def _integer(values: dict[str, JSONValue], key: str) -> int:
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Experiment A config field {key} must be an integer")
    return value


def _integer_tuple(values: dict[str, JSONValue], key: str) -> tuple[int, ...]:
    value = values.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Experiment A config field {key} must be a list")
    result = tuple(cast(int, item) for item in value)
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in value):
        raise ValueError(f"Experiment A config field {key} must contain positive integers")
    if len(set(result)) != len(result):
        raise ValueError(f"Experiment A config field {key} must not contain duplicates")
    return result


def _summary_json(summary: TrendBaselineSummary) -> dict[str, JSONValue]:
    return {
        "horizon": summary.horizon,
        "sample_size": summary.sample_size,
        "mean_return": summary.mean_return,
        "median_return": summary.median_return,
        "positive_fraction": summary.positive_fraction,
        "median_mfe": summary.median_mfe,
        "median_mae": summary.median_mae,
        "median_max_drawdown": summary.median_max_drawdown,
    }
