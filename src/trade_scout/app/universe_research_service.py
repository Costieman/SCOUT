"""Application boundary for market-wide exploratory strategy research.

The service reads one selected immutable canonical dataset and a reviewed identity candidate. It
never calls a market-data provider. The only currently enabled universe is the fully reviewed
canonical identity scope; point-in-time S&P 500 membership is deliberately not inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
    to_research_bar,
)
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.patterns.timeframes import PatternTimeframe
from trade_scout.statistics.timeframe_universe_research import (
    build_timeframe_universe_research_report,
)
from trade_scout.statistics.universe_research import UniverseResearchReport


class UniverseResearchError(RuntimeError):
    """Raised when a universe request cannot be satisfied without guessing or silent repair."""


@dataclass(frozen=True, slots=True)
class UniverseOption:
    """One explicitly supported research-universe source."""

    universe_id: str
    label: str
    point_in_time_membership: bool


@dataclass(frozen=True, slots=True)
class UniverseResearchRequest:
    """Resolved user inputs for one exploratory market-wide run."""

    universe_id: str = "reviewed_canonical"
    strategy_id: str = "consolidation_breakout"
    pattern_timeframe: PatternTimeframe = PatternTimeframe.DAILY
    lookback_years: int = 2
    horizon: int = 20
    duration: int = 20
    max_range_pct: float = 0.12
    trend_filter: TrendFilter = TrendFilter.ABOVE_SMA_50_100_200
    min_breakout_volume_ratio: float | None = None

    def __post_init__(self) -> None:
        encoded_prefix = "consolidation_breakout@"
        if self.strategy_id.startswith(encoded_prefix):
            timeframe_value = self.strategy_id.removeprefix(encoded_prefix)
            object.__setattr__(self, "pattern_timeframe", PatternTimeframe(timeframe_value))
            object.__setattr__(self, "strategy_id", "consolidation_breakout")
        if self.universe_id != "reviewed_canonical":
            raise ValueError(f"unsupported universe_id {self.universe_id!r}")
        if self.strategy_id != "consolidation_breakout":
            raise ValueError(f"unsupported strategy_id {self.strategy_id!r}")
        if self.lookback_years not in {1, 2, 3, 5, 10, 20}:
            raise ValueError("lookback_years must be one of 1, 2, 3, 5, 10, 20")
        if self.horizon not in {2, 3, 5, 10, 20, 40, 60}:
            raise ValueError("horizon must be one of 2, 3, 5, 10, 20, 40, 60")
        if not 5 <= self.duration <= 252:
            raise ValueError("duration must be between 5 and 252 pattern bars")
        if not 0 < self.max_range_pct <= 1:
            raise ValueError("max_range_pct must be in (0, 1]")
        if self.min_breakout_volume_ratio is not None and self.min_breakout_volume_ratio <= 0:
            raise ValueError("min_breakout_volume_ratio must be positive when supplied")


class UniverseResearchSource(Protocol):
    """Read-only canonical source consumed by the universe research application service."""

    def available_universes(self) -> tuple[UniverseOption, ...]: ...

    def research_series(
        self,
        universe_id: str,
    ) -> dict[str, tuple[ResearchBar, ...]]: ...


@dataclass(frozen=True, slots=True)
class CanonicalUniverseResearchSource:
    """Expose fully reviewed canonical instrument histories for exploratory research."""

    canonical_root: Path
    dataset_version: str
    identity_candidate_path: Path

    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (
            UniverseOption(
                universe_id="reviewed_canonical",
                label="Reviewed canonical equity scope — not point-in-time S&P 500",
                point_in_time_membership=False,
            ),
        )

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]:
        """Return PASS canonical rows for the exact reviewed universe, without provider calls."""

        symbol_by_instrument = self._reviewed_symbol_by_instrument(universe_id)
        canonical = CanonicalDailyBarStore(self.canonical_root).load(
            DatasetVersion(self.dataset_version)
        )
        selected = tuple(bar for bar in canonical if str(bar.instrument_id) in symbol_by_instrument)
        if not selected:
            raise UniverseResearchError(
                "selected canonical dataset contains no fully reviewed instrument histories"
            )
        non_pass = tuple(item for item in selected if item.quality_status is not QualityStatus.PASS)
        if non_pass:
            first = non_pass[0]
            symbol = symbol_by_instrument.get(str(first.instrument_id), str(first.instrument_id))
            raise UniverseResearchError(f"canonical series {symbol} contains non-PASS quality rows")
        return tuple(sorted(selected, key=lambda item: (str(item.instrument_id), item.trade_date)))

    def research_series(
        self,
        universe_id: str,
    ) -> dict[str, tuple[ResearchBar, ...]]:
        symbol_by_instrument = self._reviewed_symbol_by_instrument(universe_id)
        canonical = self.canonical_daily_bars(universe_id)
        bars_by_instrument: dict[str, list[DailyBar]] = {}
        for bar in canonical:
            bars_by_instrument.setdefault(str(bar.instrument_id), []).append(bar)

        result: dict[str, tuple[ResearchBar, ...]] = {}
        for instrument_id, symbol in sorted(symbol_by_instrument.items(), key=lambda item: item[1]):
            selected = tuple(bars_by_instrument.get(instrument_id, ()))
            if not selected:
                continue
            try:
                result[symbol] = tuple(
                    to_research_bar(
                        item,
                        representation=PriceRepresentation.SPLIT_ADJUSTED,
                        eligibility=True,
                    )
                    for item in selected
                )
            except ValueError as exc:
                raise UniverseResearchError(
                    f"split-adjusted canonical history is unavailable for {symbol}"
                ) from exc

        if not result:
            raise UniverseResearchError(
                "selected canonical dataset contains no fully reviewed instrument histories"
            )
        return dict(sorted(result.items()))

    def _reviewed_symbol_by_instrument(self, universe_id: str) -> dict[str, str]:
        if universe_id != "reviewed_canonical":
            raise UniverseResearchError(f"unsupported research universe {universe_id!r}")
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        blocked = {str(item.instrument_id) for item in candidate.coverage_gaps}
        result = {
            str(item.instrument_id): item.query_symbol.upper()
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo" and str(item.instrument_id) not in blocked
        }
        if not result:
            raise UniverseResearchError("reviewed identity scope contains no fully covered series")
        return result


@dataclass(frozen=True, slots=True)
class UniverseResearchService:
    """Resolve a user request and delegate analytics to the statistics layer."""

    source: UniverseResearchSource

    def run(self, request: UniverseResearchRequest) -> UniverseResearchReport:
        options = {item.universe_id: item for item in self.source.available_universes()}
        option = options.get(request.universe_id)
        if option is None:
            raise UniverseResearchError(f"unavailable research universe {request.universe_id!r}")

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
        horizons = tuple(sorted({2, 3, 5, 10, 20, 40, 60, request.horizon}))
        return build_timeframe_universe_research_report(
            series,
            universe_id=option.universe_id,
            universe_label=option.label,
            config=config,
            analysis_start=start,
            analysis_end=latest,
            pattern_timeframe=request.pattern_timeframe,
            selected_horizon=request.horizon,
            horizons=horizons,
        )


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "CanonicalUniverseResearchSource",
    "UniverseOption",
    "UniverseResearchError",
    "UniverseResearchRequest",
    "UniverseResearchService",
    "UniverseResearchSource",
]
