from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from trade_scout.app.market_scanner_service import (
    MarketScannerError,
    MarketScannerRequest,
    MarketScannerService,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.market_analysis import compute_market_analysis_feature_frame


def _series(
    symbol: str,
    growth: float,
    final_volume_multiplier: float,
    *,
    count: int = 260,
) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(count):
        close = 100.0 * math.exp(index * growth)
        volume = 1_000.0
        if index == count - 1:
            volume *= final_volume_multiplier
        rows.append(
            DailyBar(
                instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                trade_date=date(2023, 1, 2) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=volume,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("scanner-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class _Source:
    rows: dict[str, tuple[DailyBar, ...]]

    def canonical_series(self) -> dict[str, tuple[DailyBar, ...]]:
        return dict(self.rows)


def test_scanner_filters_and_ranks_latest_cross_section() -> None:
    source = _Source(
        {
            "FAST": _series("FAST", 0.004, 2.0),
            "MID": _series("MID", 0.002, 1.7),
            "SLOW": _series("SLOW", 0.0002, 3.0),
        }
    )
    report = MarketScannerService(source).run(
        MarketScannerRequest(
            min_return_20=0.03,
            min_relative_volume_20=1.5,
            min_distance_sma_200_pct=0.0,
            sort_by="return_20",
            limit=10,
        )
    )

    assert report.scanned_symbol_count == 3
    assert report.matched_symbol_count == 2
    assert report.unavailable_symbol_count == 0
    assert tuple(item.symbol for item in report.rows) == ("FAST", "MID")
    assert report.rows[0].return_20 is not None
    assert report.rows[0].return_20 > report.rows[1].return_20
    assert report.rows[0].relative_volume_20 == 2.0


def test_scanner_limit_is_applied_after_full_match_count() -> None:
    source = _Source(
        {
            "AAA": _series("AAA", 0.003, 1.0),
            "BBB": _series("BBB", 0.002, 1.0),
        }
    )
    report = MarketScannerService(source).run(MarketScannerRequest(limit=1))

    assert report.matched_symbol_count == 2
    assert len(report.rows) == 1
    assert report.rows[0].symbol == "AAA"


def test_bounded_latest_state_matches_full_history_feature_frame() -> None:
    bars = _series("LONG", 0.0015, 2.4, count=1_500)
    report = MarketScannerService(_Source({"LONG": bars})).run(
        MarketScannerRequest(sort_by="return_20")
    )
    row = report.rows[0]

    full = compute_market_analysis_feature_frame(bars)
    latest_date = bars[-1].trade_date
    expected = {
        item.feature_name: item.value
        for item in full
        if item.trade_date == latest_date
        and item.availability_status is FeatureAvailabilityStatus.AVAILABLE
    }

    assert row.return_20 == pytest.approx(expected["return_20"])
    assert row.return_252 == pytest.approx(expected["return_252"])
    assert row.relative_volume_20 == pytest.approx(expected["relative_volume_20"])
    assert row.realized_volatility_20 == pytest.approx(expected["realized_volatility_20"])
    assert row.atr_pct_14 == pytest.approx(expected["atr_pct_14"])
    assert row.distance_sma_50_pct == pytest.approx(expected["distance_sma_50_pct"])
    assert row.distance_sma_200_pct == pytest.approx(expected["distance_sma_200_pct"])


def test_scanner_expression_filters_latest_feature_rows() -> None:
    source = _Source(
        {
            "FAST": _series("FAST", 0.004, 2.2),
            "MID": _series("MID", 0.002, 1.8),
            "SLOW": _series("SLOW", 0.0002, 3.0),
        }
    )
    report = MarketScannerService(source).run(
        MarketScannerRequest(
            expression="return_20 > 0.05 and relative_volume_20 >= 2",
            sort_by="return_20",
        )
    )

    assert tuple(item.symbol for item in report.rows) == ("FAST",)


def test_invalid_scanner_expression_is_rejected_explicitly() -> None:
    source = _Source({"AAA": _series("AAA", 0.003, 1.0)})

    with pytest.raises(MarketScannerError, match="invalid scanner expression"):
        MarketScannerService(source).run(
            MarketScannerRequest(expression="__import__('os').system('echo nope')")
        )
