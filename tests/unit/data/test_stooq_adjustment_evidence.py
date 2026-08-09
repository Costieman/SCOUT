from __future__ import annotations

from datetime import date

from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.providers.stooq_adjustment_evidence import (
    StooqAdjustmentEvidenceState,
    characterize_stooq_split_semantics,
)


def _bar(day: str, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="stooq",
        provider_instrument_id="reviewed:example",
        symbol="TEST.US",
        trade_date=date.fromisoformat(day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        split_factor=None,
        dividend_cash=None,
    )


def test_split_probe_classifies_raw_like_discontinuity() -> None:
    evidence = characterize_stooq_split_semantics(
        (_bar("2020-08-28", 500.0), _bar("2020-08-31", 125.0)),
        symbol="TEST.US",
        split_date=date(2020, 8, 31),
        split_ratio=4.0,
    )

    assert evidence.state is StooqAdjustmentEvidenceState.RAW_LIKE
    assert evidence.observed_pre_post_ratio == 4.0


def test_split_probe_classifies_adjusted_like_continuity() -> None:
    evidence = characterize_stooq_split_semantics(
        (_bar("2020-08-28", 125.0), _bar("2020-08-31", 126.0)),
        symbol="TEST.US",
        split_date=date(2020, 8, 31),
        split_ratio=4.0,
    )

    assert evidence.state is StooqAdjustmentEvidenceState.SPLIT_ADJUSTED_LIKE


def test_split_probe_remains_inconclusive_when_market_move_confounds_hypotheses() -> None:
    evidence = characterize_stooq_split_semantics(
        (_bar("2020-08-28", 200.0), _bar("2020-08-31", 100.0)),
        symbol="TEST.US",
        split_date=date(2020, 8, 31),
        split_ratio=4.0,
    )

    assert evidence.state is StooqAdjustmentEvidenceState.INCONCLUSIVE


def test_split_probe_requires_bars_on_both_sides() -> None:
    evidence = characterize_stooq_split_semantics(
        (_bar("2020-08-28", 500.0),),
        symbol="TEST.US",
        split_date=date(2020, 8, 31),
        split_ratio=4.0,
    )

    assert evidence.state is StooqAdjustmentEvidenceState.INCONCLUSIVE
    assert evidence.post_trade_date is None
