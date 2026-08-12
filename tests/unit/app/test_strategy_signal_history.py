from __future__ import annotations

import math
from datetime import date, timedelta

from trade_scout.app.strategy_definition import StrategyDefinition
from trade_scout.app.strategy_signal_history import evaluate_strategy_signal_history
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


def _series(symbol: str, growth: float, *, final_volume_multiplier: float = 1.0) -> tuple[DailyBar, ...]:
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
                dataset_version=DatasetVersion("strategy-history-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_historical_strategy_signals_are_point_in_time_and_ranked_per_date() -> None:
    strategy = StrategyDefinition(
        strategy_id="history-test-v0.1",
        name="History Test",
        description="Select positive 20-session momentum and rank by that momentum.",
        expression="return_20 > 0.02",
        sort_by="return_20",
        descending=True,
        limit=1,
    )
    bars = (*_series("FAST", 0.004), *_series("SLOW", 0.002))

    signals = evaluate_strategy_signal_history(tuple(bars), strategy)

    assert signals
    assert {str(item.instrument_id) for item in signals} == {"tsi_fast"}
    assert len({item.trade_date for item in signals}) == len(signals)
    assert all(item.rank_feature == "return_20" for item in signals)
    assert all(item.dataset_version == DatasetVersion("strategy-history-test-v1") for item in signals)


def test_future_volume_spike_does_not_create_earlier_rvol_signal() -> None:
    strategy = StrategyDefinition(
        strategy_id="rvol-history-test-v0.1",
        name="RVOL History Test",
        description="Select only sessions with elevated relative volume.",
        expression="relative_volume_20 >= 1.5",
        sort_by="relative_volume_20",
        descending=True,
        limit=10,
    )

    signals = evaluate_strategy_signal_history(
        _series("SPIKE", 0.001, final_volume_multiplier=2.0),
        strategy,
    )

    assert len(signals) == 1
    assert signals[0].trade_date == date(2025, 1, 2) + timedelta(days=259)
    assert signals[0].rank_value == 2.0
