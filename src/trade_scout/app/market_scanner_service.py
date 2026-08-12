"""Cross-sectional scanner over reviewed canonical symbols and reusable market-analysis features."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

from trade_scout.app.market_analysis_service import MarketAnalysisSource
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DailyBar, DatasetVersion, QualityStatus
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate
from trade_scout.features.contracts import FeatureAvailabilityStatus, FeatureValue
from trade_scout.features.market_analysis import compute_market_analysis_feature_frame

ScannerSortKey = Literal[
    "return_20",
    "return_252",
    "relative_volume_20",
    "atr_pct_14",
    "realized_volatility_20",
    "distance_sma_200_pct",
]
_SORT_KEYS: frozenset[str] = frozenset(
    {
        "return_20",
        "return_252",
        "relative_volume_20",
        "atr_pct_14",
        "realized_volatility_20",
        "distance_sma_200_pct",
    }
)


class MarketScannerError(RuntimeError):
    """Raised when a scanner run cannot be completed without guessing."""


@dataclass(frozen=True, slots=True)
class MarketScannerRequest:
    min_return_20: float | None = None
    min_return_252: float | None = None
    min_relative_volume_20: float | None = None
    max_realized_volatility_20: float | None = None
    max_atr_pct_14: float | None = None
    min_distance_sma_200_pct: float | None = None
    sort_by: ScannerSortKey = "return_20"
    descending: bool = True
    limit: int = 100

    def __post_init__(self) -> None:
        if self.sort_by not in _SORT_KEYS:
            raise ValueError(f"unsupported scanner sort feature {self.sort_by!r}")
        if self.min_relative_volume_20 is not None and self.min_relative_volume_20 < 0:
            raise ValueError("min_relative_volume_20 must be non-negative")
        if self.max_realized_volatility_20 is not None and self.max_realized_volatility_20 < 0:
            raise ValueError("max_realized_volatility_20 must be non-negative")
        if self.max_atr_pct_14 is not None and self.max_atr_pct_14 < 0:
            raise ValueError("max_atr_pct_14 must be non-negative")
        if not 1 <= self.limit <= 500:
            raise ValueError("limit must be between 1 and 500")


@dataclass(frozen=True, slots=True)
class MarketScannerRow:
    symbol: str
    as_of: str
    return_20: float | None
    return_252: float | None
    relative_volume_20: float | None
    realized_volatility_20: float | None
    atr_pct_14: float | None
    distance_sma_50_pct: float | None
    distance_sma_200_pct: float | None

    def value(self, name: ScannerSortKey) -> float | None:
        values: dict[ScannerSortKey, float | None] = {
            "return_20": self.return_20,
            "return_252": self.return_252,
            "relative_volume_20": self.relative_volume_20,
            "atr_pct_14": self.atr_pct_14,
            "realized_volatility_20": self.realized_volatility_20,
            "distance_sma_200_pct": self.distance_sma_200_pct,
        }
        return values[name]


@dataclass(frozen=True, slots=True)
class MarketScannerReport:
    scanned_symbol_count: int
    matched_symbol_count: int
    unavailable_symbol_count: int
    request: MarketScannerRequest
    rows: tuple[MarketScannerRow, ...]


class MarketScannerSource(Protocol):
    """Read-only source that materializes the reviewed canonical universe once per scan."""

    def canonical_series(self) -> dict[str, tuple[DailyBar, ...]]: ...


@dataclass(frozen=True, slots=True)
class CanonicalMarketScannerSource:
    """Load one immutable canonical dataset once and map it to reviewed query symbols."""

    canonical_root: Path
    dataset_version: str
    identity_candidate_path: Path

    def canonical_series(self) -> dict[str, tuple[DailyBar, ...]]:
        candidate = load_reviewed_identity_snapshot_candidate(self.identity_candidate_path)
        blocked = {item.instrument_id for item in candidate.coverage_gaps}
        links = tuple(
            item
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo" and item.instrument_id not in blocked
        )
        canonical = CanonicalDailyBarStore(self.canonical_root).load(
            DatasetVersion(self.dataset_version)
        )
        by_instrument: dict[str, list[DailyBar]] = {}
        for bar in canonical:
            if bar.quality_status is not QualityStatus.PASS:
                raise MarketScannerError(
                    f"canonical dataset {self.dataset_version} contains non-PASS quality rows"
                )
            by_instrument.setdefault(str(bar.instrument_id), []).append(bar)

        result: dict[str, tuple[DailyBar, ...]] = {}
        for link in links:
            bars = tuple(
                sorted(
                    by_instrument.get(str(link.instrument_id), ()),
                    key=lambda item: item.trade_date,
                )
            )
            if bars:
                result[link.query_symbol.upper()] = bars
        if not result:
            raise MarketScannerError("selected canonical dataset contains no reviewed series")
        return dict(sorted(result.items()))


@dataclass(frozen=True, slots=True)
class MarketScannerService:
    source: MarketScannerSource | MarketAnalysisSource

    def run(self, request: MarketScannerRequest) -> MarketScannerReport:
        if not hasattr(self.source, "canonical_series"):
            raise MarketScannerError("scanner source does not support bulk canonical access")
        bulk_source = cast(MarketScannerSource, self.source)
        series = bulk_source.canonical_series()
        all_bars = tuple(bar for bars in series.values() for bar in bars)
        all_values = compute_market_analysis_feature_frame(all_bars)
        values_by_instrument_date: dict[tuple[str, str], dict[str, FeatureValue]] = {}
        for item in all_values:
            key = (str(item.instrument_id), item.trade_date.isoformat())
            values_by_instrument_date.setdefault(key, {})[item.feature_name] = item

        rows: list[MarketScannerRow] = []
        unavailable = 0
        for symbol, bars in series.items():
            latest_bar = bars[-1]
            latest = values_by_instrument_date.get(
                (str(latest_bar.instrument_id), latest_bar.trade_date.isoformat()),
                {},
            )
            row = MarketScannerRow(
                symbol=symbol,
                as_of=latest_bar.trade_date.isoformat(),
                return_20=_available_value(latest.get("return_20")),
                return_252=_available_value(latest.get("return_252")),
                relative_volume_20=_available_value(latest.get("relative_volume_20")),
                realized_volatility_20=_available_value(latest.get("realized_volatility_20")),
                atr_pct_14=_available_value(latest.get("atr_pct_14")),
                distance_sma_50_pct=_available_value(latest.get("distance_sma_50_pct")),
                distance_sma_200_pct=_available_value(latest.get("distance_sma_200_pct")),
            )
            if not _has_required_values(row, request):
                unavailable += 1
                continue
            if _matches(row, request):
                rows.append(row)

        rows.sort(
            key=lambda item: _sort_value(item, request.sort_by),
            reverse=request.descending,
        )
        matched = len(rows)
        return MarketScannerReport(
            scanned_symbol_count=len(series),
            matched_symbol_count=matched,
            unavailable_symbol_count=unavailable,
            request=request,
            rows=tuple(rows[: request.limit]),
        )


def _available_value(value: FeatureValue | None) -> float | None:
    if value is None:
        return None
    if value.availability_status is not FeatureAvailabilityStatus.AVAILABLE or value.value is None:
        return None
    return float(value.value)


def _has_required_values(row: MarketScannerRow, request: MarketScannerRequest) -> bool:
    required = {request.sort_by}
    if request.min_return_20 is not None:
        required.add("return_20")
    if request.min_return_252 is not None:
        required.add("return_252")
    if request.min_relative_volume_20 is not None:
        required.add("relative_volume_20")
    if request.max_realized_volatility_20 is not None:
        required.add("realized_volatility_20")
    if request.max_atr_pct_14 is not None:
        required.add("atr_pct_14")
    if request.min_distance_sma_200_pct is not None:
        required.add("distance_sma_200_pct")
    return all(getattr(row, name) is not None for name in required)


def _matches(row: MarketScannerRow, request: MarketScannerRequest) -> bool:
    checks = (
        _minimum(row.return_20, request.min_return_20),
        _minimum(row.return_252, request.min_return_252),
        _minimum(row.relative_volume_20, request.min_relative_volume_20),
        _maximum(row.realized_volatility_20, request.max_realized_volatility_20),
        _maximum(row.atr_pct_14, request.max_atr_pct_14),
        _minimum(row.distance_sma_200_pct, request.min_distance_sma_200_pct),
    )
    return all(checks)


def _minimum(value: float | None, threshold: float | None) -> bool:
    return threshold is None or (value is not None and value >= threshold)


def _maximum(value: float | None, threshold: float | None) -> bool:
    return threshold is None or (value is not None and value <= threshold)


def _sort_value(row: MarketScannerRow, name: ScannerSortKey) -> float:
    value = row.value(name)
    if value is None:
        raise MarketScannerError(f"scanner sort feature {name} is unavailable for {row.symbol}")
    return value


__all__ = [
    "CanonicalMarketScannerSource",
    "MarketScannerError",
    "MarketScannerReport",
    "MarketScannerRequest",
    "MarketScannerRow",
    "MarketScannerService",
    "MarketScannerSource",
    "ScannerSortKey",
]
