"""Application boundary for market-wide stop-policy research on a fixed breakout event set."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.app.universe_research_service import UniverseResearchSource
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
    detect_consolidation_breakouts,
)
from trade_scout.risk.initial_stops import (
    CostModel,
    RiskPolicyResult,
    evaluate_stop_policy_grid,
    initial_stop_policy_grid,
)
from trade_scout.statistics.stop_research import (
    StopResearchComparison,
    summarize_stop_policy_results,
)


class RiskResearchError(RuntimeError):
    """Raised when a stop-policy research request cannot be satisfied without guessing."""


@dataclass(frozen=True, slots=True)
class RiskResearchRequest:
    """Resolved exploratory inputs; entry-pattern parameters stay explicit and fixed for the run."""

    universe_id: str = "reviewed_canonical"
    lookback_years: int = 2
    horizon: int = 20
    duration: int = 20
    max_range_pct: float = 0.12
    trend_filter: TrendFilter = TrendFilter.ABOVE_SMA_50_100_200
    min_breakout_volume_ratio: float | None = None
    cost_bps_per_side: float = 0.0

    def __post_init__(self) -> None:
        if self.universe_id != "reviewed_canonical":
            raise ValueError(f"unsupported universe_id {self.universe_id!r}")
        if self.lookback_years not in {1, 2, 3, 5, 10, 20}:
            raise ValueError("lookback_years must be one of 1, 2, 3, 5, 10, 20")
        if self.horizon not in {2, 3, 5, 10, 20, 40, 60}:
            raise ValueError("horizon must be one of 2, 3, 5, 10, 20, 40, 60")
        if not 5 <= self.duration <= 252:
            raise ValueError("duration must be between 5 and 252 sessions")
        if not 0 < self.max_range_pct <= 1:
            raise ValueError("max_range_pct must be in (0, 1]")
        if self.min_breakout_volume_ratio is not None and self.min_breakout_volume_ratio <= 0:
            raise ValueError("min_breakout_volume_ratio must be positive when supplied")
        if not 0 <= self.cost_bps_per_side <= 500:
            raise ValueError("cost_bps_per_side must be between 0 and 500")


@dataclass(frozen=True, slots=True)
class RiskResearchReport:
    """Presentation-ready fixed-event stop-policy comparison."""

    universe_id: str
    universe_label: str
    dataset_version: str
    analysis_start: date
    analysis_end: date
    event_count: int
    selected_config: ConsolidationBreakoutConfig
    comparison: StopResearchComparison
    research_state: str = "EXPLORATORY"
    risk_program_version: str = "consolidation-stop-research-v0.1"


@dataclass(frozen=True, slots=True)
class RiskResearchService:
    """Detect the fixed event population, then delegate stop simulation and aggregation."""

    source: UniverseResearchSource

    def run(self, request: RiskResearchRequest) -> RiskResearchReport:
        options = {item.universe_id: item for item in self.source.available_universes()}
        option = options.get(request.universe_id)
        if option is None:
            raise RiskResearchError(f"unavailable research universe {request.universe_id!r}")
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
        cost_model = CostModel(
            entry_slippage_bps=request.cost_bps_per_side,
            exit_slippage_bps=request.cost_bps_per_side,
        )
        policies = initial_stop_policy_grid()
        results: list[RiskPolicyResult] = []
        event_count = 0
        dataset_versions: set[str] = set()
        for bars in series.values():
            dataset_versions.add(str(bars[0].dataset_version))
            events = tuple(
                item
                for item in detect_consolidation_breakouts(bars, config)
                if start <= item.signal_date <= latest
            )
            event_count += len(events)
            results.extend(
                evaluate_stop_policy_grid(
                    bars,
                    events,
                    horizon=request.horizon,
                    policies=policies,
                    cost_model=cost_model,
                )
            )
        if len(dataset_versions) != 1:
            raise RiskResearchError("risk research cannot mix canonical dataset versions")
        comparison = summarize_stop_policy_results(
            tuple(results),
            policies=policies,
            horizon=request.horizon,
            entry_slippage_bps=request.cost_bps_per_side,
            exit_slippage_bps=request.cost_bps_per_side,
        )
        return RiskResearchReport(
            universe_id=request.universe_id,
            universe_label=option.label,
            dataset_version=next(iter(dataset_versions)),
            analysis_start=start,
            analysis_end=latest,
            event_count=event_count,
            selected_config=config,
            comparison=comparison,
        )


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "RiskResearchError",
    "RiskResearchReport",
    "RiskResearchRequest",
    "RiskResearchService",
]
