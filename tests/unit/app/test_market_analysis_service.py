from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from trade_scout.app.market_analysis_service import (
    MarketAnalysisRequest,
    MarketAnalysisService,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus


class _Source:
    def __init__(self, bars: tuple[DailyBar, ...]) -> None:
        self._bars = bars

    def available_symbols(self) -> tuple[str, ...]:
        return ("TEST",)

    def canonical_bars(self, symbol: str) -> tuple[DailyBar, ...]:
        assert symbol.upper() == "TEST"
        return self._bars


def _bars(count: int = 260) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(count):
        close = 100.0 * math.exp(index * 0.001)
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_market_analysis_app_test"),
                trade_date=date(2024, 1, 2) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=1_000.0 + index * 10.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("market-analysis-app-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_market_analysis_service_exposes_latest_feature_pack_and_chart_window() -> None:
    bars = _bars()
    report = MarketAnalysisService(_Source(bars)).run(
        MarketAnalysisRequest(symbol="test", chart_sessions=60)
    )

    assert report.symbol == "TEST"
    assert report.dataset_version == "market-analysis-app-test-v1"
    assert report.as_of == bars[-1].trade_date
    assert len(report.metrics) == 8
    assert len(report.price_history) == 60
    assert report.price_history[0].trade_date == bars[-60].trade_date
    assert report.price_history[-1].close == bars[-1].close_split_adjusted

    return_20 = report.metric("return_20")
    assert return_20.availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert return_20.value == pytest.approx(
        bars[-1].close_split_adjusted / bars[-21].close_split_adjusted - 1
    )


def test_market_analysis_request_bounds_chart_window() -> None:
    with pytest.raises(ValueError, match="chart_sessions"):
        MarketAnalysisRequest(symbol="TEST", chart_sessions=10)
