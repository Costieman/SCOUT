"""Application service for configurable post-entry exit-policy research.

The first application harness uses the existing consolidation-breakout event family, but the exit
engine itself is strategy-neutral and consumes only the shared ``EventRecord`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.app.universe_research_service import UniverseResearchSource
from trade_scout.events import detect_consolidation_events
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
    evaluate_exit_policy_grid,
    exit_policy_grid,
)
from trade_scout.risk.initial_stops import CostModel
from trade_scout.statistics.exit_research import (
    ExitResearchComparison,
    summarize_exit_policy_results,
)


class ExitPolicyLabError(RuntimeError):
    """Raised when a configurable exit-policy experiment cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ExitPolicyLabRequest:
    """Fully resolved operator inputs for one exit-policy family comparison."""

    universe_id: str = "reviewed_canonical"
    lookback_years: int = 2
    horizon: int = 20
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
class ExitPolicyLabReport:
    """Presentation-ready output from one configurable exit experiment."""

    universe_id: str
    universe_label: str
    dataset_version: str
    analysis_start: date
    analysis_end: date
    detected_event_count: int
    selected_config: ConsolidationBreakoutConfig
    policies: tuple[ExitPolicy, ...]
    comparison: ExitResearchComparison
    research_state: str = "EXPLORATORY"
    application_version: str = "exit-policy-lab-v0.2"
    event_definition_version: str = "consolidation-close-breakout-v0.3"


@dataclass(frozen=True, slots=True)
class ExitPolicyLabService:
    """Freeze events once, then compare configurable exit policies on the common population."""

    source: UniverseResearchSource

    def run(self, request: ExitPolicyLabRequest) -> ExitPolicyLabReport:
        options = {item.universe_id: item for item in self.source.available_universes()}
        option = options.get(request.universe_id)
        if option is None:
            raise ExitPolicyLabError(f"unavailable research universe {request.universe_id!r}")
        series = self.source.research_series(request.universe_id)
        latest = max(bars[-1].trade_date for bars in series.values())
        start = _subtract_years(latest, request.lookback_years)
        config = ConsolidationBreakoutConfig(
            duration=request.duration,
            max_range_pct=request.max_range_pct,
            trend_filter=request.trend_filter,
            cooldown_sessions=5,
            min_breakout_volume_ratio=request.min_breakout_volume_ratio,
            volume_lookback_sessions=20,
        )
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
        results: list[ExitPolicyResult] = []
        event_count = 0
        dataset_versions: set[str] = set()
        for bars in series.values():
            dataset_versions.add(str(bars[0].dataset_version))
            events = tuple(
                event
                for event in detect_consolidation_events(bars, config)
                if start <= event.signal_date <= latest
            )
            event_count += len(events)
            results.extend(
                evaluate_exit_policy_grid(
                    bars,
                    events,
                    horizon=request.horizon,
                    policies=policies,
                    cost_model=cost_model,
                )
            )
        if len(dataset_versions) != 1:
            raise ExitPolicyLabError("exit-policy lab cannot mix canonical dataset versions")
        comparison = summarize_exit_policy_results(
            tuple(results),
            policies=policies,
            horizon=request.horizon,
        )
        return ExitPolicyLabReport(
            universe_id=request.universe_id,
            universe_label=option.label,
            dataset_version=next(iter(dataset_versions)),
            analysis_start=start,
            analysis_end=latest,
            detected_event_count=event_count,
            selected_config=config,
            policies=policies,
            comparison=comparison,
        )


def parse_percentage_grid(value: str) -> tuple[float, ...]:
    """Parse UI/CLI percentage points such as ``2,3,5`` into decimal fractions."""

    values = _parse_positive_grid(value, field="percentage grid")
    decimals = tuple(item / 100.0 for item in values)
    if any(item >= 1.0 for item in decimals):
        raise ValueError("percentage grid values must be below 100")
    return decimals


def parse_multiple_grid(value: str) -> tuple[float, ...]:
    """Parse positive ATR multiples such as ``1,1.5,2``."""

    return _parse_positive_grid(value, field="ATR multiple grid")


def _parse_positive_grid(value: str, *, field: str) -> tuple[float, ...]:
    if not value.strip():
        return ()
    try:
        result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be a comma-separated numeric list") from exc
    if any(item <= 0 for item in result):
        raise ValueError(f"{field} values must be positive")
    if len(set(result)) != len(result):
        raise ValueError(f"{field} values must not contain duplicates")
    return result


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "ExitPolicyLabError",
    "ExitPolicyLabReport",
    "ExitPolicyLabRequest",
    "ExitPolicyLabService",
    "parse_multiple_grid",
    "parse_percentage_grid",
]
