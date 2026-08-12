"""Application service exposing reusable market-analysis features for one reviewed symbol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DailyBar, DatasetVersion, QualityStatus
from trade_scout.data.reviewed_identity_snapshot import (
    load_reviewed_identity_snapshot_candidate,
    provider_series_link_for_query,
)
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.market_analysis import (
    MARKET_ANALYSIS_FEATURE_SET_VERSION,
    MarketAnalysisFeatureInputError,
    compute_market_analysis_feature_frame,
)


class MarketAnalysisError(RuntimeError):
    """Raised when a market-analysis request cannot be satisfied without guessing."""


@dataclass(frozen=True, slots=True)
class MarketAnalysisRequest:
    symbol: str
    chart_sessions: int = 120

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not 20 <= self.chart_sessions <= 504:
            raise ValueError("chart_sessions must be between 20 and 504")


@dataclass(frozen=True, slots=True)
class MarketAnalysisMetric:
    feature_name: str
    value: float | None
    units: str
    availability_status: FeatureAvailabilityStatus


@dataclass(frozen=True, slots=True)
class MarketAnalysisPricePoint:
    trade_date: date
    close: float


@dataclass(frozen=True, slots=True)
class MarketAnalysisReport:
    symbol: str
    dataset_version: str
    feature_set_version: str
    as_of: date
    metrics: tuple[MarketAnalysisMetric, ...]
    price_history: tuple[MarketAnalysisPricePoint, ...]

    def metric(self, feature_name: str) -> MarketAnalysisMetric:
        for item in self.metrics:
            if item.feature_name == feature_name:
                return item
        raise KeyError(feature_name)


class MarketAnalysisSource(Protocol):
    """Read-only source consumed by the market-analysis application service."""

    def available_symbols(self) -> tuple[str, ...]: ...

    def canonical_bars(self, symbol: str) -> tuple[DailyBar, ...]: ...


@dataclass(frozen=True, slots=True)
class CanonicalMarketAnalysisSource:
    """Resolve reviewed symbols to one immutable canonical daily-bar dataset."""

    canonical_root: Path
    dataset_version: str
    identity_candidate_path: Path

    def available_symbols(self) -> tuple[str, ...]:
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        blocked = {item.instrument_id for item in candidate.coverage_gaps}
        return tuple(
            sorted(
                item.query_symbol.upper()
                for item in candidate.provider_series_links
                if item.provider_id == "tiingo" and item.instrument_id not in blocked
            )
        )

    def canonical_bars(self, symbol: str) -> tuple[DailyBar, ...]:
        normalized = symbol.strip().upper()
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        link = provider_series_link_for_query(
            candidate,
            provider_id="tiingo",
            query_symbol=normalized,
        )
        if link is None:
            raise MarketAnalysisError(
                f"{normalized} is not in the reviewed identity scope available to Market Analysis"
            )
        if any(item.instrument_id == link.instrument_id for item in candidate.coverage_gaps):
            raise MarketAnalysisError(
                f"{normalized} has unresolved reviewed identity/history coverage and is blocked"
            )

        canonical = CanonicalDailyBarStore(self.canonical_root).load(
            DatasetVersion(self.dataset_version)
        )
        selected = tuple(item for item in canonical if item.instrument_id == link.instrument_id)
        if not selected:
            raise MarketAnalysisError(
                f"canonical dataset {self.dataset_version} contains no rows for {normalized}"
            )
        if any(item.quality_status is not QualityStatus.PASS for item in selected):
            raise MarketAnalysisError(
                f"canonical rows for {normalized} include non-PASS quality states; analysis is blocked"
            )
        return tuple(sorted(selected, key=lambda item: item.trade_date))


@dataclass(frozen=True, slots=True)
class MarketAnalysisService:
    source: MarketAnalysisSource

    def run(self, request: MarketAnalysisRequest) -> MarketAnalysisReport:
        bars = self.source.canonical_bars(request.symbol)
        try:
            values = compute_market_analysis_feature_frame(bars)
        except MarketAnalysisFeatureInputError as exc:
            raise MarketAnalysisError(str(exc)) from exc

        latest_date = bars[-1].trade_date
        latest_values = tuple(item for item in values if item.trade_date == latest_date)
        metrics = tuple(
            MarketAnalysisMetric(
                feature_name=item.feature_name,
                value=item.value,
                units=item.units,
                availability_status=item.availability_status,
            )
            for item in latest_values
        )
        price_history = tuple(
            MarketAnalysisPricePoint(
                trade_date=item.trade_date,
                close=_required_close(item),
            )
            for item in bars[-request.chart_sessions :]
        )
        return MarketAnalysisReport(
            symbol=request.symbol.strip().upper(),
            dataset_version=str(bars[-1].dataset_version),
            feature_set_version=MARKET_ANALYSIS_FEATURE_SET_VERSION,
            as_of=latest_date,
            metrics=metrics,
            price_history=price_history,
        )


def _required_close(bar: DailyBar) -> float:
    value = bar.close_split_adjusted
    if value is None:
        raise MarketAnalysisError(
            f"split-adjusted close is unavailable for {bar.instrument_id} on {bar.trade_date}"
        )
    return value


__all__ = [
    "CanonicalMarketAnalysisSource",
    "MarketAnalysisError",
    "MarketAnalysisMetric",
    "MarketAnalysisPricePoint",
    "MarketAnalysisReport",
    "MarketAnalysisRequest",
    "MarketAnalysisService",
    "MarketAnalysisSource",
]
