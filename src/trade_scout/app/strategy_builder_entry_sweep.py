"""Application service for one-variable parameter sweeps of entry indicators."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from time import perf_counter

from trade_scout.app.strategy_builder_service import (
    StrategyBuilderError,
    StrategyBuilderRequest,
    StrategyBuilderSource,
    WindowedStrategyBuilderSource,
)
from trade_scout.data.contracts import DailyBar, PriceRepresentation, ResearchBar, to_research_bar
from trade_scout.events.contracts import EventRecord
from trade_scout.features.parameterized_expression import (
    extract_parameterized_specs,
    parse_parameterized_feature_name,
)
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    ParameterizedIndicatorSpec,
    compute_parameterized_indicator_frame,
)
from trade_scout.risk.exit_policies import ExitPolicyResult, evaluate_exit_policy_grid, exit_policy_grid
from trade_scout.risk.initial_stops import CostModel
from trade_scout.statistics.exit_research import summarize_exit_policy_results
from trade_scout.statistics.strategy_family_research import run_feature_strategy_signal_family
from trade_scout.statistics.strategy_research import StrategyDefinition, required_strategy_warmup_observations


class EntrySweepParameter(StrEnum):
    """Indicator parameters permitted as the single entry-sweep dimension."""

    PERIOD = "period"
    STANDARD_DEVIATIONS = "standard_deviations"
    FAST_PERIOD = "fast_period"
    SLOW_PERIOD = "slow_period"
    SIGNAL_PERIOD = "signal_period"


@dataclass(frozen=True, slots=True)
class EntrySweepPoint:
    """Descriptive hold-to-horizon result for one predeclared entry-parameter value."""

    value: float
    resolved_feature_name: str
    entry_event_count: int
    complete_event_count: int
    expectancy: float | None
    win_probability: float | None
    profit_factor: float | None
    tail_loss_p05: float | None
    average_holding_period_sessions: float | None


@dataclass(frozen=True, slots=True)
class StrategyBuilderEntrySweepReport:
    """Complete one-dimensional entry-parameter response surface."""

    target_feature_name: str
    parameter: EntrySweepParameter
    parameter_label: str
    unit_label: str
    values: tuple[float, ...]
    points: tuple[EntrySweepPoint, ...]
    dataset_version: str
    analysis_start: date
    analysis_end: date
    search_space_fingerprint: str
    total_seconds: float
    research_state: str = "EXPLORATORY"
    definition_version: str = "strategy-builder-entry-sweep-v0.1"


@dataclass(frozen=True, slots=True)
class StrategyBuilderEntrySweepService:
    """Evaluate one entry-indicator parameter range while keeping all other entry rules fixed."""

    source: StrategyBuilderSource
    progress: Callable[[str], None] | None = None

    def run(
        self,
        base_request: StrategyBuilderRequest,
        *,
        target_feature_name: str,
        parameter: EntrySweepParameter,
        values: tuple[float, ...],
    ) -> StrategyBuilderEntrySweepReport:
        started = perf_counter()
        if base_request.entry_family.value != "feature_expression":
            raise StrategyBuilderError("entry-parameter sweeps require the feature-expression entry family")
        if not isinstance(self.source, WindowedStrategyBuilderSource):
            raise StrategyBuilderError("entry-parameter sweeps require the window-aware canonical source")
        if not values:
            raise ValueError("entry sweep requires at least one value")
        if len(values) > 30:
            raise ValueError("entry sweeps are limited to 30 predeclared values")
        if len(set(values)) != len(values):
            raise ValueError("entry sweep values must not contain duplicates")

        base_specs = extract_parameterized_specs(base_request.expression)
        by_name = {item.feature_name: item for item in base_specs}
        base_spec = by_name.get(target_feature_name)
        if base_spec is None:
            raise ValueError("entry sweep target must be a parameterized indicator in the current entry definition")
        _validate_parameter_for_spec(base_spec, parameter)

        latest = self.source.strategy_builder_latest_trade_date(base_request.universe_id)
        signal_start = _subtract_years(latest, base_request.lookback_years)
        strategies: list[StrategyDefinition] = []
        variant_specs: dict[str, ParameterizedIndicatorSpec] = {}
        resolved_names: list[str] = []
        for index, raw_value in enumerate(values):
            resolved_spec = _replace_parameter(base_spec, parameter, raw_value)
            resolved_names.append(resolved_spec.feature_name)
            variant_specs[resolved_spec.feature_name] = resolved_spec
            expression = base_request.expression.replace(
                target_feature_name,
                resolved_spec.feature_name,
            )
            strategies.append(
                StrategyDefinition(
                    strategy_id=f"strategy-builder-entry-sweep-{index:03d}",
                    name=f"Strategy Builder entry sweep {index + 1}",
                    expression=expression,
                    rank_feature=base_request.rank_feature,
                    descending=base_request.descending,
                    per_session_limit=base_request.per_session_limit,
                    description="One-variable entry-indicator parameter sweep child.",
                )
            )
            for spec in extract_parameterized_specs(expression):
                variant_specs[spec.feature_name] = spec

        fixed_warmup = max(required_strategy_warmup_observations(item) for item in strategies)
        parameterized_warmup = max(
            (item.minimum_observations for item in variant_specs.values()),
            default=1,
        )
        working_daily_bars = self.source.strategy_builder_daily_bars(
            base_request.universe_id,
            signal_start=signal_start,
            signal_end=latest,
            warmup_observations=max(fixed_warmup, parameterized_warmup),
        )
        _progress(self.progress, f"Entry sweep | loaded {len(working_daily_bars):,} canonical bars")

        extra_features = compute_parameterized_indicator_frame(
            working_daily_bars,
            tuple(variant_specs.values()),
        )
        _progress(
            self.progress,
            f"Entry sweep | materialized {len(variant_specs)} resolved indicator outputs",
        )
        family_reports = run_feature_strategy_signal_family(
            working_daily_bars,
            strategies=tuple(strategies),
            signal_start=signal_start,
            signal_end=latest,
            extra_features=extra_features,
        )
        exit_series = _research_series_from_daily_bars(working_daily_bars)
        research_by_instrument = {
            str(series_bars[0].instrument_id): series_bars
            for series_bars in exit_series.values()
            if series_bars
        }
        policies = exit_policy_grid(
            fixed_percentages=(),
            atr_multiples=(),
            trailing_percentages=(),
            trailing_atr_multiples=(),
        )
        cost_model = CostModel(
            entry_slippage_bps=base_request.entry_slippage_bps,
            exit_slippage_bps=base_request.exit_slippage_bps,
            stop_slippage_bps=base_request.stop_slippage_bps,
            commission_bps_per_side=base_request.commission_bps_per_side,
        )

        points: list[EntrySweepPoint] = []
        for index, report in enumerate(family_reports):
            events_by_instrument: dict[str, list[EventRecord]] = {}
            for signal in report.signals:
                events_by_instrument.setdefault(str(signal.instrument_id), []).append(signal)
            results: list[ExitPolicyResult] = []
            for instrument_id, events in sorted(events_by_instrument.items()):
                bars = research_by_instrument.get(instrument_id)
                if bars is None:
                    raise StrategyBuilderError(
                        f"entry sweep event references instrument outside research series: {instrument_id}"
                    )
                results.extend(
                    evaluate_exit_policy_grid(
                        bars,
                        tuple(events),
                        horizon=base_request.horizon,
                        policies=policies,
                        cost_model=cost_model,
                    )
                )
            comparison = summarize_exit_policy_results(
                tuple(results),
                policies=policies,
                horizon=base_request.horizon,
            )
            summary = comparison.policy_summaries[0]
            points.append(
                EntrySweepPoint(
                    value=values[index],
                    resolved_feature_name=resolved_names[index],
                    entry_event_count=report.signal_count,
                    complete_event_count=comparison.complete_event_count,
                    expectancy=summary.expectancy,
                    win_probability=summary.win_probability,
                    profit_factor=summary.profit_factor,
                    tail_loss_p05=summary.tail_loss_p05,
                    average_holding_period_sessions=summary.average_holding_period_sessions,
                )
            )
            _progress(
                self.progress,
                f"Entry sweep | {parameter.value}={values[index]:g}: "
                f"{report.signal_count} entries, {comparison.complete_event_count} complete",
            )

        dataset_versions = {str(item.dataset_version) for item in working_daily_bars}
        if len(dataset_versions) != 1:
            raise StrategyBuilderError("entry sweep cannot mix canonical dataset versions")
        fingerprint_payload = "|".join(
            (
                base_request.expression,
                target_feature_name,
                parameter.value,
                *(f"{value:.12g}" for value in values),
            )
        )
        total_seconds = perf_counter() - started
        return StrategyBuilderEntrySweepReport(
            target_feature_name=target_feature_name,
            parameter=parameter,
            parameter_label=_parameter_label(base_spec, parameter),
            unit_label=_unit_label(parameter),
            values=values,
            points=tuple(points),
            dataset_version=next(iter(dataset_versions)),
            analysis_start=signal_start,
            analysis_end=latest,
            search_space_fingerprint=sha256(fingerprint_payload.encode("utf-8")).hexdigest(),
            total_seconds=total_seconds,
        )


def materialize_entry_sweep_values(
    *,
    start: float,
    end: float,
    step: float,
    parameter: EntrySweepParameter,
) -> tuple[float, ...]:
    """Resolve a declared inclusive range deterministically before execution."""

    start_decimal = Decimal(str(start))
    end_decimal = Decimal(str(end))
    step_decimal = Decimal(str(step))
    if step_decimal <= 0:
        raise ValueError("entry sweep step must be greater than zero")
    if end_decimal < start_decimal:
        raise ValueError("entry sweep end must be greater than or equal to start")
    values: list[float] = []
    value = start_decimal
    while value <= end_decimal:
        resolved = float(value)
        if parameter is not EntrySweepParameter.STANDARD_DEVIATIONS and not resolved.is_integer():
            raise ValueError("indicator period sweeps require whole trading-day values")
        values.append(resolved)
        if len(values) > 30:
            raise ValueError("entry sweeps are limited to 30 predeclared values")
        value += step_decimal
    return tuple(values)


def _replace_parameter(
    spec: ParameterizedIndicatorSpec,
    parameter: EntrySweepParameter,
    value: float,
) -> ParameterizedIndicatorSpec:
    if parameter is EntrySweepParameter.STANDARD_DEVIATIONS:
        return replace(spec, standard_deviations=value)
    integer = int(value)
    if float(integer) != value:
        raise ValueError(f"{parameter.value} must be a whole number of trading sessions")
    return replace(spec, **{parameter.value: integer})


def _validate_parameter_for_spec(
    spec: ParameterizedIndicatorSpec,
    parameter: EntrySweepParameter,
) -> None:
    if parameter is EntrySweepParameter.STANDARD_DEVIATIONS:
        if spec.family is not IndicatorFamily.BOLLINGER_BANDS:
            raise ValueError("standard-deviation sweep applies only to Bollinger Bands")
        return
    if parameter in {
        EntrySweepParameter.FAST_PERIOD,
        EntrySweepParameter.SLOW_PERIOD,
        EntrySweepParameter.SIGNAL_PERIOD,
    }:
        if spec.family is not IndicatorFamily.MACD:
            raise ValueError("MACD period sweep applies only to MACD indicators")
        return
    if parameter is EntrySweepParameter.PERIOD and spec.family is IndicatorFamily.MACD:
        raise ValueError("use fast, slow, or signal period for MACD sweeps")


def _parameter_label(spec: ParameterizedIndicatorSpec, parameter: EntrySweepParameter) -> str:
    family = spec.family.value.replace("_", " ").title()
    labels = {
        EntrySweepParameter.PERIOD: f"{family} period",
        EntrySweepParameter.STANDARD_DEVIATIONS: "Bollinger standard deviations",
        EntrySweepParameter.FAST_PERIOD: "MACD fast EMA period",
        EntrySweepParameter.SLOW_PERIOD: "MACD slow EMA period",
        EntrySweepParameter.SIGNAL_PERIOD: "MACD signal EMA period",
    }
    return labels[parameter]


def _unit_label(parameter: EntrySweepParameter) -> str:
    if parameter is EntrySweepParameter.STANDARD_DEVIATIONS:
        return "standard deviations"
    return "trading days"


def _research_series_from_daily_bars(
    bars: tuple[DailyBar, ...],
) -> dict[str, tuple[ResearchBar, ...]]:
    grouped: dict[str, list[DailyBar]] = {}
    for bar in bars:
        grouped.setdefault(str(bar.instrument_id), []).append(bar)
    result: dict[str, tuple[ResearchBar, ...]] = {}
    for instrument_id, rows in grouped.items():
        ordered = tuple(sorted(rows, key=lambda item: item.trade_date))
        result[instrument_id] = tuple(
            to_research_bar(
                item,
                representation=PriceRepresentation.SPLIT_ADJUSTED,
                eligibility=True,
            )
            for item in ordered
        )
    if not result:
        raise StrategyBuilderError("entry sweep working window contains no research series")
    return result


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


def _progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)


__all__ = [
    "EntrySweepParameter",
    "EntrySweepPoint",
    "StrategyBuilderEntrySweepReport",
    "StrategyBuilderEntrySweepService",
    "materialize_entry_sweep_values",
]
