"""Application service for the research-only Edge Explorer.

The UI calls this service; it does not calculate patterns or outcomes itself. The initial
implementation reads an already-promoted canonical daily-bar dataset and a reviewed identity
candidate. It never calls a market-data provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import (
    DatasetVersion,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
    to_research_bar,
)
from trade_scout.data.reviewed_identity_snapshot import (
    load_reviewed_identity_snapshot_candidate,
    provider_series_link_for_query,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.statistics.edge_explorer import EdgeExplorerReport, build_consolidation_edge_report


class EdgeExplorerError(RuntimeError):
    """Raised when a preview request cannot be satisfied without guessing."""


@dataclass(frozen=True, slots=True)
class EdgeExplorerRequest:
    symbol: str
    strategy_id: str = "consolidation_breakout"
    horizon: int = 20
    duration: int = 20
    max_range_pct: float = 0.12
    trend_filter: TrendFilter = TrendFilter.ABOVE_RISING_SMA_200

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.strategy_id != "consolidation_breakout":
            raise ValueError(f"unsupported strategy_id {self.strategy_id!r}")
        if self.horizon not in {5, 10, 20, 40, 60}:
            raise ValueError("horizon must be one of 5, 10, 20, 40, 60")


class EdgeExplorerSource(Protocol):
    """Read-only provider-neutral source for one exploratory analysis request."""

    def available_symbols(self) -> tuple[str, ...]: ...

    def research_bars(self, symbol: str) -> tuple[ResearchBar, ...]: ...


@dataclass(frozen=True, slots=True)
class CanonicalEdgeExplorerSource:
    """Load split-adjusted ResearchBars from one immutable canonical dataset."""

    canonical_root: Path
    dataset_version: str
    identity_candidate_path: Path

    def available_symbols(self) -> tuple[str, ...]:
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        return tuple(
            sorted(
                item.query_symbol.upper()
                for item in candidate.provider_series_links
                if item.provider_id == "tiingo"
                and not any(gap.instrument_id == item.instrument_id for gap in candidate.coverage_gaps)
            )
        )

    def research_bars(self, symbol: str) -> tuple[ResearchBar, ...]:
        normalized = symbol.strip().upper()
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        link = provider_series_link_for_query(
            candidate,
            provider_id="tiingo",
            query_symbol=normalized,
        )
        if link is None:
            raise EdgeExplorerError(
                f"{normalized} is not in the reviewed identity scope available to Edge Explorer"
            )
        gaps = tuple(item for item in candidate.coverage_gaps if item.instrument_id == link.instrument_id)
        if gaps:
            raise EdgeExplorerError(
                f"{normalized} has unresolved reviewed identity/history coverage and is blocked"
            )

        version = DatasetVersion(self.dataset_version)
        canonical = CanonicalDailyBarStore(self.canonical_root).load(version)
        selected = tuple(item for item in canonical if item.instrument_id == link.instrument_id)
        if not selected:
            raise EdgeExplorerError(
                f"canonical dataset {self.dataset_version} contains no rows for {normalized}"
            )
        if any(item.quality_status is not QualityStatus.PASS for item in selected):
            raise EdgeExplorerError(
                f"canonical rows for {normalized} include non-PASS quality states; analysis is blocked"
            )
        try:
            return tuple(
                to_research_bar(
                    item,
                    representation=PriceRepresentation.SPLIT_ADJUSTED,
                    eligibility=True,
                )
                for item in selected
            )
        except ValueError as exc:
            raise EdgeExplorerError(
                f"split-adjusted canonical history is unavailable for {normalized}"
            ) from exc


@dataclass(frozen=True, slots=True)
class EdgeExplorerService:
    source: EdgeExplorerSource

    def run(self, request: EdgeExplorerRequest) -> EdgeExplorerReport:
        bars = self.source.research_bars(request.symbol)
        if len(bars) < max(220, request.duration + request.horizon + 1):
            raise EdgeExplorerError(
                f"{request.symbol.upper()} has only {len(bars)} usable sessions; "
                "the requested definition needs more history"
            )
        config = ConsolidationBreakoutConfig(
            duration=request.duration,
            max_range_pct=request.max_range_pct,
            trend_filter=request.trend_filter,
            cooldown_sessions=5,
        )
        return build_consolidation_edge_report(
            bars,
            symbol=request.symbol,
            config=config,
            selected_horizon=request.horizon,
        )
