"""Application boundary for ad hoc feature-expression strategy research.

The service resolves a browser request against one immutable canonical dataset and the reviewed
identity scope, then delegates all analytical work to the statistics layer. It never calls a
market-data provider and never treats exploratory results as validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DailyBar, DatasetVersion, QualityStatus
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    StrategyResearchReport,
    available_strategy_features,
    run_feature_strategy_research,
)


class StrategyResearchError(RuntimeError):
    """Raised when a strategy request cannot be satisfied without guessing or repair."""


@dataclass(frozen=True, slots=True)
class StrategyResearchRequest:
    """Resolved user inputs for one exploratory feature-expression run."""

    expression: str
    rank_feature: str = "return_20"
    descending: bool = True
    per_session_limit: int = 25
    horizons: tuple[int, ...] = (5, 20, 60)
    lookback_years: int = 5
    symbols: tuple[str, ...] = ()
    strategy_id: str = "adhoc-feature-strategy-v0.1"
    name: str = "Ad hoc feature strategy"

    def __post_init__(self) -> None:
        if not self.expression.strip():
            raise ValueError("strategy expression must be non-empty")
        if self.rank_feature not in available_strategy_features():
            raise ValueError(f"unknown rank feature {self.rank_feature!r}")
        if not 1 <= self.per_session_limit <= 500:
            raise ValueError("per_session_limit must be between 1 and 500")
        if not self.horizons or any(item < 1 for item in self.horizons):
            raise ValueError("horizons must contain positive session counts")
        if len(set(self.horizons)) != len(self.horizons):
            raise ValueError("horizons must not contain duplicates")
        if self.lookback_years not in {1, 2, 3, 5, 10, 20}:
            raise ValueError("lookback_years must be one of 1, 2, 3, 5, 10, 20")
        normalized = tuple(item.strip().upper() for item in self.symbols if item.strip())
        if len(normalized) != len(set(normalized)):
            raise ValueError("symbols must not contain duplicates")
        object.__setattr__(self, "symbols", normalized)


class StrategyResearchSource(Protocol):
    """Read-only canonical source consumed by the strategy research service."""

    def available_symbols(self) -> tuple[str, ...]: ...

    def canonical_bars(self, symbols: tuple[str, ...] = ()) -> tuple[DailyBar, ...]: ...


@dataclass(frozen=True, slots=True)
class CanonicalStrategyResearchSource:
    """Expose reviewed canonical DailyBar histories without provider calls."""

    canonical_root: Path
    dataset_version: str
    identity_candidate_path: Path

    def available_symbols(self) -> tuple[str, ...]:
        links = self._reviewed_links()
        return tuple(sorted(link.query_symbol.upper() for link in links))

    def canonical_bars(self, symbols: tuple[str, ...] = ()) -> tuple[DailyBar, ...]:
        links = self._reviewed_links()
        instrument_by_symbol = {
            link.query_symbol.upper(): str(link.instrument_id) for link in links
        }
        requested = tuple(item.strip().upper() for item in symbols if item.strip())
        missing = tuple(item for item in requested if item not in instrument_by_symbol)
        if missing:
            raise StrategyResearchError(
                "unknown or blocked reviewed symbols: " + ", ".join(missing)
            )
        selected_ids = (
            {instrument_by_symbol[item] for item in requested}
            if requested
            else set(instrument_by_symbol.values())
        )
        canonical = CanonicalDailyBarStore(self.canonical_root).load(
            DatasetVersion(self.dataset_version)
        )
        selected = tuple(item for item in canonical if str(item.instrument_id) in selected_ids)
        if not selected:
            raise StrategyResearchError("selected reviewed scope has no canonical rows")
        if any(item.quality_status is not QualityStatus.PASS for item in selected):
            raise StrategyResearchError("selected canonical scope contains non-PASS quality rows")
        present_ids = {str(item.instrument_id) for item in selected}
        absent_ids = selected_ids - present_ids
        if absent_ids:
            symbol_by_instrument = {
                instrument: symbol for symbol, instrument in instrument_by_symbol.items()
            }
            absent_symbols = tuple(
                sorted(symbol_by_instrument.get(item, item) for item in absent_ids)
            )
            raise StrategyResearchError(
                "selected canonical dataset is missing reviewed symbols: "
                + ", ".join(absent_symbols)
            )
        return selected

    def _reviewed_links(self):
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        blocked = {item.instrument_id for item in candidate.coverage_gaps}
        links = tuple(
            item
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo" and item.instrument_id not in blocked
        )
        if not links:
            raise StrategyResearchError("reviewed identity scope contains no fully covered series")
        return links


@dataclass(frozen=True, slots=True)
class StrategyResearchService:
    """Resolve a user request and delegate strategy analytics to the statistics layer."""

    source: StrategyResearchSource

    def run(self, request: StrategyResearchRequest) -> StrategyResearchReport:
        bars = self.source.canonical_bars(request.symbols)
        latest = max(item.trade_date for item in bars)
        start = _subtract_years(latest, request.lookback_years)
        strategy = StrategyDefinition(
            strategy_id=request.strategy_id,
            name=request.name,
            description="Browser-supplied exploratory feature expression",
            expression=request.expression,
            rank_feature=request.rank_feature,
            descending=request.descending,
            per_session_limit=request.per_session_limit,
        )
        return run_feature_strategy_research(
            bars,
            strategy=strategy,
            horizons=request.horizons,
            signal_start=start,
            signal_end=latest,
        )


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "CanonicalStrategyResearchSource",
    "StrategyResearchError",
    "StrategyResearchRequest",
    "StrategyResearchService",
    "StrategyResearchSource",
]
