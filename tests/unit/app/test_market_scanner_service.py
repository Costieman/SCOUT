from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.app.market_scanner_service import MarketScannerRequest, MarketScannerService
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


def _series(symbol: str, growth: float, final_volume_multiplier: float) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(260):
        close = 100.0 * math.exp(index * growth)
        volume = 1_000.0
        if index == 259:
            volume *= final_volume_multiplier
        rows.append(
            DailyBar(
                instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                trade_date=date(2025, 1, 2) + timedelta(days=index),
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

    def available_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.rows))

    def canonical_bars(self, symbol: str) -> tuple[DailyBar, ...]:
        return self.rows[symbol]


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
