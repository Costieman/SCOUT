from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.app.historical_strategy_research_service import HistoricalStrategyResearchService
from trade_scout.app.strategy_definition import StrategyDefinition
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


def _series(symbol: str, growth: float) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(300):
        close = 100.0 * math.exp(index * growth)
        rows.append(
            DailyBar(
                instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                trade_date=date(2024, 1, 2) + timedelta(days=index),
                open_raw=close,
                high_raw=close * 1.01,
                low_raw=close * 0.99,
                close_raw=close,
                volume_raw=1_000.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close * 1.01,
                low_split_adjusted=close * 0.99,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("historical-strategy-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class _Source:
    rows: dict[str, tuple[DailyBar, ...]]

    def canonical_series(self) -> dict[str, tuple[DailyBar, ...]]:
        return dict(self.rows)


def test_historical_strategy_research_combines_signals_and_forward_summaries() -> None:
    strategy = StrategyDefinition(
        strategy_id="historical-test-v0.1",
        name="Historical Test",
        description="Select stronger positive 20-session momentum.",
        expression="return_20 > 0.02",
        sort_by="return_20",
        descending=True,
        limit=1,
    )
    source = _Source({"FAST": _series("FAST", 0.004), "SLOW": _series("SLOW", 0.001)})

    report = HistoricalStrategyResearchService(source).run(strategy, horizons=(5, 20))

    assert report.instrument_count == 2
    assert report.signal_count > 0
    assert {str(item.instrument_id) for item in report.signals} == {"tsi_fast"}
    assert tuple(item.horizon for item in report.summaries) == (5, 20)
    assert all(item.sample_size > 0 for item in report.summaries)
    assert all(item.mean_return is not None and item.mean_return > 0 for item in report.summaries)
