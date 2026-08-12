"""Cross-sectional scanner over reviewed canonical symbols and reusable market-analysis features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from trade_scout.app.market_analysis_service import MarketAnalysisSource
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.market_analysis import compute_market_analysis_feature_frame

ScannerSortKey = Literal[
    "return_20",
    "return_252",
    "relative_volume_20",
    "atr_pct_14",
    "realized_volatility_20",
    "distance_sma_200_pct",
]


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
        return getattr(self, name)


@dataclass(frozen=True, slots=True)
class MarketScannerReport:
    scanned_symbol_count: int
    matched_symbol_count: int
    unavailable_symbol_count: int
    request: MarketScannerRequest
    rows: tuple[MarketScannerRow, ...]


@dataclass(frozen=True, slots=True)
class MarketScannerService:
    source: MarketAnalysisSource

    def run(self, request: MarketScannerRequest) -> MarketScannerReport:
        symbols = self.source.available_symbols()
        rows: list[MarketScannerRow] = []
        unavailable = 0
        for symbol in symbols:
            bars = self.source.canonical_bars(symbol)
            values = compute_market_analysis_feature_frame(bars)
            latest_date = bars[-1].trade_date
            latest = {
                item.feature_name: item
                for item in values
                if item.trade_date == latest_date
            }
            row = MarketScannerRow(
                symbol=symbol,
                as_of=latest_date.isoformat(),
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
            scanned_symbol_count=len(symbols),
            matched_symbol_count=matched,
            unavailable_symbol_count=unavailable,
            request=request,
            rows=tuple(rows[: request.limit]),
        )


def _available_value(value: object | None) -> float | None:
    if value is None:
        return None
    status = getattr(value, "availability_status", None)
    raw = getattr(value, "value", None)
    if status is not FeatureAvailabilityStatus.AVAILABLE or raw is None:
        return None
    return float(raw)


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
    "MarketScannerError",
    "MarketScannerReport",
    "MarketScannerRequest",
    "MarketScannerRow",
    "MarketScannerService",
    "ScannerSortKey",
]
