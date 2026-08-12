from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.app.strategy_definition import MOMENTUM_RVOL_TREND
from trade_scout.app.strategy_runner_service import StrategyRunnerService
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


def _series(symbol: str, growth: float, final_volume_multiplier: float) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(260):
        close = 100.0 * math.exp(index * growth)
        volume = 1_000.0 * (final_volume_multiplier if index == 259 else 1.0)
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
                dataset_version=DatasetVersion("strategy-runner-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class _Source:
    rows: dict[str, tuple[DailyBar, ...]]

    def canonical_series(self) -> dict[str, tuple[DailyBar, ...]]:
        return dict(self.rows)


def test_strategy_runner_uses_shared_scanner_semantics() -> None:
    source = _Source(
        {
            "FAST": _series("FAST", 0.004, 2.0),
            "SLOW": _series("SLOW", 0.0002, 2.0),
        }
    )

    report = StrategyRunnerService(source).run(MOMENTUM_RVOL_TREND)

    assert report.strategy.strategy_id == "momentum-rvol-trend-v0.1"
    assert report.scanned_symbol_count == 2
    assert report.matched_symbol_count == 1
    assert tuple(item.symbol for item in report.scanner_report.rows) == ("FAST",)
