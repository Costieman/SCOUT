"""Application service composing registered entries with the shared exit-policy engine.

The builder deliberately separates setup selection from post-entry management. Entry families emit
shared ``EventRecord``-compatible records; every configured exit policy then operates on the exact
same complete event population without changing the entry definition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Protocol, runtime_checkable

from trade_scout.app.entry_strategy_registry import (
    EntryFamily,
    EntryStrategyOption,
    entry_strategy_option,
)
from trade_scout.app.strategy_presets import StrategyPreset, strategy_preset
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.app.visual_rule_builder import VisualCondition, VisualRuleSet
from trade_scout.common.stage_cache import BoundedStageCache, StageFingerprint
from trade_scout.data.contracts import (
    DailyBar,
    PriceRepresentation,
    ResearchBar,
    to_research_bar,
)
from trade_scout.events import detect_consolidation_events
from trade_scout.events.contracts import EventRecord
from trade_scout.features.contracts import FeatureValue
from trade_scout.features.parameterized_expression import extract_parameterized_specs
from trade_scout.features.parameterized_indicators import (
    PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION,
    ParameterizedIndicatorSpec,
    compute_parameterized_indicator_frame,
)
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
)
from trade_scout.risk.exit_policies import (
    DEFAULT_ATR_GRID,
    DEFAULT_FIXED_PERCENT_GRID,
    DEFAULT_TRAILING_ATR_GRID,
    DEFAULT_TRAILING_PERCENT_GRID,
    ExitPolicy,
    ExitPolicyResult,
    ManagedExitPlan,
    SameBarExitPolicy,
    evaluate_exit_policy_grid,
    exit_policy_grid,
    managed_exit_policy_grid,
)
from trade_scout.risk.initial_stops import CostModel
from trade_scout.statistics.exit_research import (
    ExitResearchComparison,
    summarize_exit_policy_results,
)
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    StrategyResearchReport,
    available_strategy_features,
    required_strategy_warmup_observations,
    run_feature_strategy_research,
)

_INDICATOR_CACHE: BoundedStageCache[tuple[FeatureValue, ...]] = BoundedStageCache(max_entries=4)
_INDICATOR_STAGE_VERSION = "strategy-builder-parameterized-indicators-v1"


class StrategyBuilderError(RuntimeError):
    """Raised when a composed entry/exit experiment cannot be resolved safely."""


class StrategyBuilderSource(Protocol):
    """Read-only canonical source required by the strategy builder."""

    def available_universes(self) -> tuple[UniverseOption, ...]: ...

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]: ...

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]: ...


@runtime_checkable
class WindowedStrategyBuilderSource(Protocol):
    """Optional fast-path source that can fetch only the Strategy Builder working window."""

    def strategy_builder_latest_trade_date(self, universe_id: str) -> date: ...

    def strategy_builder_dataset_record_count(self, universe_id: str) -> int: ...

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]: ...


@dataclass(frozen=True, slots=True)
class StrategyBuilderRequest:
    """Fully resolved entry, selection, exit, and cost choices for one exploratory run."""

    universe_id: str = "reviewed_canonical"
    lookback_years: int = 2
    horizon: int = 20
    entry_family: EntryFamily = EntryFamily.FEATURE_EXPRESSION
    preset_id: str | None = None
    visual_conditions: tuple[VisualCondition, ...] = ()
    expression: str = "return_20 >= 0.05 and relative_volume_20 >= 1.5 and distance_sma_200_pct > 0"
    rank_feature: str = "return_20"
    descending: bool = True
    per_session_limit: int = 25
    duration: int = 20
    max_range_pct: float = 0.12
    trend_filter: TrendFilter = TrendFilter.ABOVE_SMA_50_100_200
    min_breakout_volume_ratio: float | None = None
    fixed_percentages: tuple[float, ...] = DEFAULT_FIXED_PERCENT_GRID
    atr_multiples: tuple[float, ...] = DEFAULT_ATR_GRID
    trailing_percentages: tuple[float, ...] = DEFAULT_TRAILING_PERCENT_GRID
    trailing_atr_multiples: tuple[float, ...] = DEFAULT_TRAILING_ATR_GRID
    managed_exit_plans: tuple[ManagedExitPlan, ...] = ()
    same_bar_policy: SameBarExitPolicy = SameBarExitPolicy.STOP_FIRST
    entry_slippage_bps: float = 0.0
    exit_slippage_bps: float = 0.0
    stop_slippage_bps: float = 0.0
    commission_bps_per_side: float = 0.0

    def __post_init__(self) -> None:
        if self.universe_id != "reviewed_canonical":
            raise ValueError(f"unsupported universe_id {self.universe_id!r}")
        if self.lookback_years not in {1, 2, 3, 5, 10, 20}:
            raise ValueError("lookback_years must be one of 1, 2, 3, 5, 10, 20")
        if self.horizon not in {2, 3, 5, 10, 20, 40, 60, 120, 252}:
            raise ValueError("unsupported research horizon")
        entry_strategy_option(self.entry_family)
        if self.entry_family is EntryFamily.FEATURE_EXPRESSION:
            if self.visual_conditions and self.preset_id is not None:
                raise ValueError("visual rules and strategy presets cannot be selected together")
            if self.visual_conditions:
                object.__setattr__(
                    self, "expression", VisualRuleSet(self.visual_conditions).expression
                )
            elif self.preset_id is not None:
                strategy_preset(self.preset_id)
            elif not self.expression.strip():
                raise ValueError(
                    "feature-expression entry requires visual rules, a preset, or an expression"
                )
            if self.rank_feature not in available_strategy_features():
                raise ValueError(f"unknown rank feature {self.rank_feature!r}")
            if not 1 <= self.per_session_limit <= 500:
                raise ValueError("per_session_limit must be between 1 and 500")
        elif self.preset_id is not None or self.visual_conditions:
            raise ValueError(
                "visual rules and feature presets apply only to feature-expression entries"
            )
        if not 5 <= self.duration <= 252:
            raise ValueError("duration must be between 5 and 252 sessions")
        if not 0 < self.max_range_pct <= 1:
            raise ValueError("max_range_pct must be in (0, 1]")
        if self.min_breakout_volume_ratio is not None and self.min_breakout_volume_ratio <= 0:
            raise ValueError("min_breakout_volume_ratio must be positive when supplied")
        for field, values, upper in (
            ("fixed_percentages", self.fixed_percentages, 1.0),
            ("trailing_percentages", self.trailing_percentages, 1.0),
            ("atr_multiples", self.atr_multiples, None),
            ("trailing_atr_multiples", self.trailing_atr_multiples, None),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field} must not contain duplicates")
            if any(value <= 0 for value in values):
                raise ValueError(f"{field} values must be positive")
            if upper is not None and any(value >= upper for value in values):
                raise ValueError(f"{field} values must be below 100%")
        if len(set(self.managed_exit_plans)) != len(self.managed_exit_plans):
            raise ValueError("managed_exit_plans must not contain duplicates")
        if any(
            plan.same_bar_policy is not self.same_bar_policy for plan in self.managed_exit_plans
        ):
            raise ValueError("all managed exit plans must use the request same-bar policy")
        costs = (
            self.entry_slippage_bps,
            self.exit_slippage_bps,
            self.stop_slippage_bps,
            self.commission_bps_per_side,
        )
        if any(value < 0 or value > 500 for value in costs):
            raise ValueError("execution-cost fields must be between 0 and 500 bps")


@dataclass(frozen=True, slots=True)
class StrategyBuilderPerformance:
    """Small operator-facing performance record for one synchronous research run."""

    dataset_daily_bar_count: int
    canonical_daily_bar_count: int
    working_daily_bar_count: int
    phase_seconds: tuple[tuple[str, float], ...]
    total_seconds: float
    version: str = "strategy-builder-performance-v0.2"


@dataclass(frozen=True, slots=True)
class StrategyBuilderReport:
    """Presentation-ready evidence from one composed entry/exit experiment."""

    universe_id: str
    universe_label: str
    dataset_version: str
    analysis_start: date
    analysis_end: date
    entry_option: EntryStrategyOption
    entry_event_count: int
    entry_definition_version: str
    visual_conditions: tuple[VisualCondition, ...]
    parameterized_indicator_specs: tuple[ParameterizedIndicatorSpec, ...]
    feature_preset: StrategyPreset | None
    feature_strategy_report: StrategyResearchReport | None
    consolidation_config: ConsolidationBreakoutConfig | None
    policies: tuple[ExitPolicy, ...]
    comparison: ExitResearchComparison
    performance: StrategyBuilderPerformance
    provider_calls_made: bool = False
    research_state: str = "EXPLORATORY"
    application_version: str = "strategy-builder-v0.8"


@dataclass(frozen=True, slots=True)
class StrategyBuilderService:
    """Compose one registered setup family with one configurable exit-policy family."""

    source: StrategyBuilderSource
    progress: Callable[[str], None] | None = None

    def run(self, request: StrategyBuilderRequest) -> StrategyBuilderReport:
        run_started = perf_counter()
        phases: list[tuple[str, float]] = []

        def phase(name: str, started: float) -> float:
            elapsed = perf_counter() - started
            phases.append((name, elapsed))
            if self.progress is not None:
                self.progress(f"Strategy Builder | {name}: {elapsed:.2f}s")
            return perf_counter()

        if self.progress is not None:
            self.progress("Strategy Builder | starting research run")

        started = perf_counter()
        options = {item.universe_id: item for item in self.source.available_universes()}
        option = options.get(request.universe_id)
        if option is None:
            raise StrategyBuilderError(f"unavailable research universe {request.universe_id!r}")
        entry_option = entry_strategy_option(request.entry_family)

        parameterized_specs: tuple[ParameterizedIndicatorSpec, ...] = ()
        feature_preset: StrategyPreset | None = None
        feature_report: StrategyResearchReport | None = None
        consolidation_config: ConsolidationBreakoutConfig | None = None
        events_by_instrument: dict[str, list[EventRecord]] = {}
        dataset_daily_bar_count = 0
        canonical_daily_bar_count = 0
        working_daily_bar_count = 0
        exit_series: dict[str, tuple[ResearchBar, ...]] = {}

        if request.entry_family is EntryFamily.FEATURE_EXPRESSION and isinstance(
            self.source, WindowedStrategyBuilderSource
        ):
            latest = self.source.strategy_builder_latest_trade_date(request.universe_id)
            start = _subtract_years(latest, request.lookback_years)
            dataset_daily_bar_count = self.source.strategy_builder_dataset_record_count(
                request.universe_id
            )
            started = phase("load research universe", started)

            feature_preset, strategy_definition = _feature_strategy_definition(request)
            parameterized_specs = extract_parameterized_specs(strategy_definition.expression)
            fixed_warmup = required_strategy_warmup_observations(strategy_definition)
            parameterized_warmup = max(
                (item.minimum_observations for item in parameterized_specs),
                default=1,
            )
            working_daily_bars = self.source.strategy_builder_daily_bars(
                request.universe_id,
                signal_start=start,
                signal_end=latest,
                warmup_observations=max(fixed_warmup, parameterized_warmup),
            )
            canonical_daily_bar_count = len(working_daily_bars)
            working_daily_bar_count = len(working_daily_bars)
            exit_series = _research_series_from_daily_bars(working_daily_bars)
            started = phase("load canonical daily bars", started)
            started = phase("bound working history", started)

            extra_features, cache_hit = _materialize_requested_indicators(
                working_daily_bars,
                parameterized_specs,
                universe_id=request.universe_id,
            )
            if self.progress is not None:
                self.progress(
                    "Strategy Builder | parameterized indicator cache: "
                    + ("HIT" if cache_hit else "MISS")
                )
            started = phase("materialize requested indicators", started)

            feature_report = run_feature_strategy_research(
                working_daily_bars,
                strategy=strategy_definition,
                horizons=(request.horizon,),
                signal_start=start,
                signal_end=latest,
                extra_features=extra_features,
                measure_outcomes=False,
            )
            for signal in feature_report.signals:
                events_by_instrument.setdefault(str(signal.instrument_id), []).append(signal)
            entry_count = feature_report.signal_count
            entry_definition_version = entry_option.definition_version
            started = phase("select frozen entry population", started)
        else:
            series = self.source.research_series(request.universe_id)
            if not series:
                raise StrategyBuilderError("strategy builder received an empty research universe")
            latest = max(series_bars[-1].trade_date for series_bars in series.values())
            start = _subtract_years(latest, request.lookback_years)
            dataset_daily_bar_count = sum(len(series_bars) for series_bars in series.values())
            exit_series = series
            started = phase("load research universe", started)

            if request.entry_family is EntryFamily.FEATURE_EXPRESSION:
                feature_preset, strategy_definition = _feature_strategy_definition(request)
                daily_bars = self.source.canonical_daily_bars(request.universe_id)
                canonical_daily_bar_count = len(daily_bars)
                started = phase("load canonical daily bars", started)

                parameterized_specs = extract_parameterized_specs(strategy_definition.expression)
                fixed_warmup = required_strategy_warmup_observations(strategy_definition)
                parameterized_warmup = max(
                    (item.minimum_observations for item in parameterized_specs),
                    default=1,
                )
                working_daily_bars, first_dates = _trim_daily_bars_for_signal_window(
                    daily_bars,
                    signal_start=start,
                    signal_end=latest,
                    warmup_observations=max(fixed_warmup, parameterized_warmup),
                )
                working_daily_bar_count = len(working_daily_bars)
                exit_series = _trim_research_series_to_daily_window(
                    series,
                    working_daily_bars,
                    first_dates,
                    latest,
                )
                started = phase("bound working history", started)

                extra_features, cache_hit = _materialize_requested_indicators(
                    working_daily_bars,
                    parameterized_specs,
                    universe_id=request.universe_id,
                )
                if self.progress is not None:
                    self.progress(
                        "Strategy Builder | parameterized indicator cache: "
                        + ("HIT" if cache_hit else "MISS")
                    )
                started = phase("materialize requested indicators", started)

                feature_report = run_feature_strategy_research(
                    working_daily_bars,
                    strategy=strategy_definition,
                    horizons=(request.horizon,),
                    signal_start=start,
                    signal_end=latest,
                    extra_features=extra_features,
                    measure_outcomes=False,
                )
                for signal in feature_report.signals:
                    events_by_instrument.setdefault(str(signal.instrument_id), []).append(signal)
                entry_count = feature_report.signal_count
                entry_definition_version = entry_option.definition_version
                started = phase("select frozen entry population", started)
            else:
                entry_count = 0
                consolidation_config = ConsolidationBreakoutConfig(
                    duration=request.duration,
                    max_range_pct=request.max_range_pct,
                    trend_filter=request.trend_filter,
                    cooldown_sessions=5,
                    min_breakout_volume_ratio=request.min_breakout_volume_ratio,
                    volume_lookback_sessions=20,
                )
                for series_bars in series.values():
                    detected_events = tuple(
                        event
                        for event in detect_consolidation_events(series_bars, consolidation_config)
                        if start <= event.signal_date <= latest
                    )
                    entry_count += len(detected_events)
                    if detected_events:
                        events_by_instrument.setdefault(
                            str(series_bars[0].instrument_id), []
                        ).extend(detected_events)
                entry_definition_version = entry_option.definition_version
                started = phase("select frozen entry population", started)

        policies = (
            managed_exit_policy_grid(request.managed_exit_plans)
            if request.managed_exit_plans
            else exit_policy_grid(
                fixed_percentages=request.fixed_percentages,
                atr_multiples=request.atr_multiples,
                trailing_percentages=request.trailing_percentages,
                trailing_atr_multiples=request.trailing_atr_multiples,
            )
        )
        cost_model = CostModel(
            entry_slippage_bps=request.entry_slippage_bps,
            exit_slippage_bps=request.exit_slippage_bps,
            stop_slippage_bps=request.stop_slippage_bps,
            commission_bps_per_side=request.commission_bps_per_side,
        )
        research_by_instrument = {
            str(series_bars[0].instrument_id): series_bars
            for series_bars in exit_series.values()
            if series_bars
        }
        results: list[ExitPolicyResult] = []
        for instrument_id, entry_events in sorted(events_by_instrument.items()):
            instrument_bars = research_by_instrument.get(instrument_id)
            if instrument_bars is None:
                raise StrategyBuilderError(
                    f"entry event references instrument outside research series: {instrument_id}"
                )
            results.extend(
                evaluate_exit_policy_grid(
                    instrument_bars,
                    tuple(entry_events),
                    horizon=request.horizon,
                    policies=policies,
                    cost_model=cost_model,
                )
            )
        started = phase("evaluate exit policies", started)

        versions = {
            str(series_bars[0].dataset_version)
            for series_bars in exit_series.values()
            if series_bars
        }
        if len(versions) != 1:
            raise StrategyBuilderError("strategy builder cannot mix canonical dataset versions")
        comparison = summarize_exit_policy_results(
            tuple(results),
            policies=policies,
            horizon=request.horizon,
        )
        phase("summarize research results", started)

        total_seconds = perf_counter() - run_started
        if self.progress is not None:
            self.progress(
                "Strategy Builder | complete: "
                f"{entry_count} entries, {comparison.complete_event_count} complete events, "
                f"{total_seconds:.2f}s total"
            )
        performance = StrategyBuilderPerformance(
            dataset_daily_bar_count=dataset_daily_bar_count,
            canonical_daily_bar_count=canonical_daily_bar_count,
            working_daily_bar_count=working_daily_bar_count,
            phase_seconds=tuple(phases),
            total_seconds=total_seconds,
        )
        return StrategyBuilderReport(
            universe_id=request.universe_id,
            universe_label=option.label,
            dataset_version=next(iter(versions)),
            analysis_start=start,
            analysis_end=latest,
            entry_option=entry_option,
            entry_event_count=entry_count,
            entry_definition_version=entry_definition_version,
            visual_conditions=request.visual_conditions,
            parameterized_indicator_specs=parameterized_specs,
            feature_preset=feature_preset,
            feature_strategy_report=feature_report,
            consolidation_config=consolidation_config,
            policies=policies,
            comparison=comparison,
            performance=performance,
        )


def _feature_strategy_definition(
    request: StrategyBuilderRequest,
) -> tuple[StrategyPreset | None, StrategyDefinition]:
    if request.preset_id is not None:
        preset = strategy_preset(request.preset_id)
        return preset, preset.definition()
    return None, StrategyDefinition(
        strategy_id=(
            "strategy-builder-visual-rules"
            if request.visual_conditions
            else "strategy-builder-custom-expression"
        ),
        name=(
            "Strategy Builder visual rule set"
            if request.visual_conditions
            else "Strategy Builder custom expression"
        ),
        expression=request.expression,
        rank_feature=request.rank_feature,
        descending=request.descending,
        per_session_limit=request.per_session_limit,
        description=(
            "Operator-composed point-in-time visual rule set."
            if request.visual_conditions
            else "Operator-defined point-in-time Strategy Builder expression."
        ),
    )


def _materialize_requested_indicators(
    bars: tuple[DailyBar, ...],
    specs: tuple[ParameterizedIndicatorSpec, ...],
    *,
    universe_id: str,
) -> tuple[tuple[FeatureValue, ...], bool]:
    """Reuse deterministic indicator outputs across runs with unchanged upstream inputs."""

    if not specs:
        return (), True
    if not bars:
        raise ValueError("parameterized indicator cache requires canonical daily bars")
    versions = {str(item.dataset_version) for item in bars}
    if len(versions) != 1:
        raise ValueError("parameterized indicator cache cannot mix canonical dataset versions")

    scope: dict[str, list[date]] = {}
    for bar in bars:
        scope.setdefault(str(bar.instrument_id), []).append(bar.trade_date)
    canonical_scope = tuple(
        (
            instrument_id,
            min(dates).isoformat(),
            max(dates).isoformat(),
            len(dates),
        )
        for instrument_id, dates in sorted(scope.items())
    )
    resolved_specs = tuple(
        sorted(
            (
                spec.feature_name,
                tuple(sorted(dict(spec.resolved_parameters).items())),
            )
            for spec in specs
        )
    )
    fingerprint = StageFingerprint.build(
        stage="parameterized_indicators",
        version=_INDICATOR_STAGE_VERSION,
        dependencies={
            "dataset_version": next(iter(versions)),
            "universe_id": universe_id,
            "feature_set_version": PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION,
            "canonical_scope": canonical_scope,
            "resolved_specs": resolved_specs,
        },
    )
    cached = _INDICATOR_CACHE.get(fingerprint)
    if cached is not None:
        return cached, True
    computed = compute_parameterized_indicator_frame(bars, specs)
    _INDICATOR_CACHE.put(fingerprint, computed)
    return computed, False


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
        raise StrategyBuilderError("working canonical window contains no research series")
    return result


def _trim_daily_bars_for_signal_window(
    bars: tuple[DailyBar, ...],
    *,
    signal_start: date,
    signal_end: date,
    warmup_observations: int,
) -> tuple[tuple[DailyBar, ...], dict[str, date]]:
    if warmup_observations < 1:
        raise ValueError("warmup_observations must be positive")
    grouped: dict[str, list[DailyBar]] = {}
    for bar in bars:
        if bar.trade_date <= signal_end:
            grouped.setdefault(str(bar.instrument_id), []).append(bar)

    selected: list[DailyBar] = []
    first_dates: dict[str, date] = {}
    for instrument_id, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: item.trade_date)
        first_signal_index = next(
            (index for index, item in enumerate(ordered) if item.trade_date >= signal_start),
            len(ordered),
        )
        if first_signal_index >= len(ordered):
            continue
        first_index = max(0, first_signal_index - warmup_observations)
        retained = ordered[first_index:]
        if not retained:
            continue
        first_dates[instrument_id] = retained[0].trade_date
        selected.extend(retained)
    if not selected:
        raise StrategyBuilderError("requested strategy window contains no canonical daily bars")
    return tuple(
        sorted(selected, key=lambda item: (str(item.instrument_id), item.trade_date))
    ), first_dates


def _trim_research_series_to_daily_window(
    series: dict[str, tuple[ResearchBar, ...]],
    working_daily_bars: tuple[DailyBar, ...],
    first_dates: dict[str, date],
    latest: date,
) -> dict[str, tuple[ResearchBar, ...]]:
    daily_dates: dict[str, list[date]] = {}
    for bar in working_daily_bars:
        daily_dates.setdefault(str(bar.instrument_id), []).append(bar.trade_date)

    trimmed: dict[str, tuple[ResearchBar, ...]] = {}
    for key, rows in series.items():
        if not rows:
            continue
        instrument_id = str(rows[0].instrument_id)
        first_date = first_dates.get(instrument_id)
        if first_date is None:
            continue
        retained = tuple(bar for bar in rows if first_date <= bar.trade_date <= latest)
        if tuple(item.trade_date for item in retained) != tuple(daily_dates[instrument_id]):
            raise StrategyBuilderError(
                "canonical daily bars and research-series dates diverged after window trimming for "
                f"{instrument_id}"
            )
        trimmed[key] = retained
    if not trimmed:
        raise StrategyBuilderError("working research series is empty after history bounding")
    return trimmed


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "StrategyBuilderError",
    "StrategyBuilderPerformance",
    "StrategyBuilderReport",
    "StrategyBuilderRequest",
    "StrategyBuilderService",
    "StrategyBuilderSource",
    "WindowedStrategyBuilderSource",
]
