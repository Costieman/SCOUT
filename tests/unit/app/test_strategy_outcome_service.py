from __future__ import annotations

from datetime import date, timedelta

from trade_scout.app.strategy_outcome_service import (
    measure_strategy_forward_outcomes,
    summarize_strategy_outcomes,
)
from trade_scout.app.strategy_signal_history import StrategySignal
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


def _bars() -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(10):
        close = 100.0 + index
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_test"),
                trade_date=date(2026, 1, 2) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 2.0,
                low_raw=close - 2.0,
                close_raw=close + 1.0,
                volume_raw=1_000.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 2.0,
                low_split_adjusted=close - 2.0,
                close_split_adjusted=close + 1.0,
                provider_id="synthetic",
                dataset_version=DatasetVersion("strategy-outcome-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_strategy_outcomes_use_next_session_open_and_complete_horizon() -> None:
    signal = StrategySignal(
        strategy_id="test-v0.1",
        instrument_id=InstrumentId("tsi_test"),
        trade_date=date(2026, 1, 4),
        rank_feature="return_20",
        rank_value=0.1,
        dataset_version=DatasetVersion("strategy-outcome-test-v1"),
        feature_set_version="market-analysis-features-v0.1",
    )

    outcomes = measure_strategy_forward_outcomes(_bars(), (signal,), horizons=(3,))

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.signal_date == "2026-01-04"
    assert outcome.entry_date == "2026-01-05"
    assert outcome.entry_price == 103.0
    assert outcome.exit_date == "2026-01-07"
    assert outcome.exit_price == 106.0
    assert outcome.forward_return == 106.0 / 103.0 - 1.0
    assert outcome.outcome_definition_version == "strategy-next-open-split-adjusted-v0.1"


def test_incomplete_forward_horizon_is_absent_and_summary_is_explicit() -> None:
    signal = StrategySignal(
        strategy_id="test-v0.1",
        instrument_id=InstrumentId("tsi_test"),
        trade_date=date(2026, 1, 10),
        rank_feature="return_20",
        rank_value=0.1,
        dataset_version=DatasetVersion("strategy-outcome-test-v1"),
        feature_set_version="market-analysis-features-v0.1",
    )

    outcomes = measure_strategy_forward_outcomes(_bars(), (signal,), horizons=(5,))
    summaries = summarize_strategy_outcomes(outcomes, (5,))

    assert outcomes == ()
    assert summaries[0].sample_size == 0
    assert summaries[0].mean_return is None
