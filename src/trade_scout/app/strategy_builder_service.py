"""Application service composing registered entries with the shared exit-policy engine.

The builder deliberately separates setup selection from post-entry management. Entry families emit
shared ``EventRecord``-compatible records; every configured exit policy then operates on the exact
same complete event population without changing the entry definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from trade_scout.app.entry_strategy_registry import (
    EntryFamily,
    EntryStrategyOption,
    entry_strategy_option,
)
from trade_scout.app.strategy_presets import StrategyPreset, strategy_preset
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import DailyBar, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
    detect_consolidation_breakouts,
)
from trade_scout.risk.exit_policies import (
    DEFAULT_ATR_GRID,
    DEFAULT_FIXED_PERCENT_GRID,
    DEFAULT_TRAILING_ATR_GRID,
    DEFAULT_TRAILING_PERCENT_GRID,
    ExitPolicy,
    ExitPolicyResult,
    evaluate_exit_policy_grid,
    exit_policy_grid,
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
    run_feature_strategy_research,
)


class StrategyBuilderError(RuntimeError):
    """Raised when a composed entry/exit experiment cannot be resolved safely."""


class StrategyBuilderSource(Protocol):
    """Read-only canonical source required by the strategy builder."""

    def available_universes(self) -> tuple[UniverseOption, ...]: ...

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]: ...

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]: ...


@dataclass(frozen=True, slots=True)
class StrategyBuilderRequest:
    """Fully resolved entry, selection, exit, and cost choices for one exploratory run."""

    universe_id: str = "reviewed_canonical"
    lookback_years: int = 2
    horizon: int = 20
    entry_family: EntryFamily = EntryFamily.FEATURE_EXPRESSION
    preset_id: str | None = None
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
            if self.preset_id is not None:
                strategy_preset(self.preset_id)
            elif not self.expression.strip():
                raise ValueError(
                    "feature-expression entry requires a preset or non-empty expression"
                )
            if self.rank_feature not in available_strategy_features():
                raise ValueError(f"unknown rank feature {self.rank_feature!r}")
            if not 1 <= self.per_session_limit <= 500:
                raise ValueError("per_session_limit must be between 1 and 500")
        elif self.preset_id is not None:
            raise ValueError("feature presets apply only to feature-expression entries")
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
        costs = (
            self.entry_slippage_bps,
            self.exit_slippage_bps,
            self.stop_slippage_bps,
            self.commission_bps_per_side,
        )
        if any(value < 0 or value > 500 for value in costs):
            raise ValueError("execution-cost fields must be between 0 and 500 bps")


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
    feature_preset: StrategyPreset | None
    feature_strategy_report: StrategyResearchReport | None
    consolidation_config: ConsolidationBreakoutConfig | None
    policies: tuple[ExitPolicy, ...]
    comparison: ExitResearchComparison
    provider_calls_made: bool = False
    research_state: str = "EXPLORATORY"
    application_version: str = "strategy-builder-v0.2"


@dataclass(frozen=True, slots=True)
class StrategyBuilderService:
    """Compose one registered setup family with one configurable exit-policy family."""

    source: StrategyBuilderSource

    def run(self, request: StrategyBuilderRequest) -> StrategyBuilderReport:
        options = {item.universe_id: item for item in self.source.available_universes()}
        option = options.get(request.universe_id)
        if option is None:
            raise StrategyBuilderError(f"unavailable research universe {request.universe_id!r}")
        series = self.source.research_series(request.universe_id)
        if not series:
            raise StrategyBuilderError("strategy builder received an empty research universe")
        latest = max(series_bars[-1].trade_date for series_bars in series.values())
        start = _subtract_years(latest, request.lookback_years)
        entry_option = entry_strategy_option(request.entry_family)

        feature_preset: StrategyPreset | None = None
        feature_report: StrategyResearchReport | None = None
        consolidation_config: ConsolidationBreakoutConfig | None = None
        events_by_instrument: dict[str, list[EventRecord]] = {}
        if request.entry_family is EntryFamily.FEATURE_EXPRESSION:
            feature_preset, strategy_definition = _feature_strategy_definition(request)
            feature_report = run_feature_strategy_research(
                self.source.canonical_daily_bars(request.universe_id),
                strategy=strategy_definition,
                horizons=(request.horizon,),
                signal_start=start,
                signal_end=latest,
            )
            for signal in feature_report.signals:
                events_by_instrument.setdefault(str(signal.instrument_id), []).append(signal)
            entry_count = feature_report.signal_count
            entry_definition_version = entry_option.definition_version
        else:
            consolidation_config = ConsolidationBreakoutConfig(
                duration=request.duration,
                max_range_pct=request.max_range_pct,
                trend_filter=request.trend_filter,
                cooldown_sessions=5,
                min_breakout_volume_ratio=request.min_breakout_volume_ratio,
                volume_lookback_sessions=20,
            )
            entry_count = 0
            for series_bars in series.values():
                detected_events = tuple(
                    event
                    for event in detect_consolidation_breakouts(series_bars, consolidation_config)
                    if start <= event.signal_date <= latest
                )
                entry_count += len(detected_events)
                if detected_events:
                    events_by_instrument.setdefault(str(series_bars[0].instrument_id), []).extend(
                        detected_events
                    )
            entry_definition_version = entry_option.definition_version

        policies = exit_policy_grid(
            fixed_percentages=request.fixed_percentages,
            atr_multiples=request.atr_multiples,
            trailing_percentages=request.trailing_percentages,
            trailing_atr_multiples=request.trailing_atr_multiples,
        )
        cost_model = CostModel(
            entry_slippage_bps=request.entry_slippage_bps,
            exit_slippage_bps=request.exit_slippage_bps,
            stop_slippage_bps=request.stop_slippage_bps,
            commission_bps_per_side=request.commission_bps_per_side,
        )
        research_by_instrument = {
            str(series_bars[0].instrument_id): series_bars
            for series_bars in series.values()
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

        versions = {
            str(series_bars[0].dataset_version) for series_bars in series.values() if series_bars
        }
        if len(versions) != 1:
            raise StrategyBuilderError("strategy builder cannot mix canonical dataset versions")
        comparison = summarize_exit_policy_results(
            tuple(results),
            policies=policies,
            horizon=request.horizon,
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
            feature_preset=feature_preset,
            feature_strategy_report=feature_report,
            consolidation_config=consolidation_config,
            policies=policies,
            comparison=comparison,
        )


def _feature_strategy_definition(
    request: StrategyBuilderRequest,
) -> tuple[StrategyPreset | None, StrategyDefinition]:
    if request.preset_id is not None:
        preset = strategy_preset(request.preset_id)
        return preset, preset.definition()
    return None, StrategyDefinition(
        strategy_id="strategy-builder-custom-expression",
        name="Strategy Builder custom expression",
        expression=request.expression,
        rank_feature=request.rank_feature,
        descending=request.descending,
        per_session_limit=request.per_session_limit,
        description="Operator-defined point-in-time Strategy Builder expression.",
    )


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "StrategyBuilderError",
    "StrategyBuilderReport",
    "StrategyBuilderRequest",
    "StrategyBuilderService",
    "StrategyBuilderSource",
]
