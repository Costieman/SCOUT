from datetime import date

import pytest

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.provider import ProviderCorporateAction, ProviderDailyBar
from trade_scout.data.providers.tiingo import TiingoResponseError
from trade_scout.data.providers.tiingo_adjustments import apply_tiingo_split_adjustments


def _bar(day: int, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="tiingo",
        provider_instrument_id="tiingo:AAPL",
        symbol="AAPL",
        trade_date=date(2020, 8, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        split_factor=None,
        dividend_cash=0.0,
    )


def _split(day: int, ratio: float) -> ProviderCorporateAction:
    return ProviderCorporateAction(
        provider_id="tiingo",
        provider_instrument_id="tiingo:AAPL",
        source_event_id=None,
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2020, 8, day),
        source_fields={"splitFactor": ratio},
    )


def test_four_for_one_split_adjusts_only_pre_effective_date() -> None:
    bars = (_bar(28, 400.0), _bar(31, 100.0))
    adjusted = apply_tiingo_split_adjustments(
        bars,
        (_split(31, 4.0),),
        adjustment_anchor_date=date(2020, 8, 31),
    )

    assert adjusted[0].split_factor == pytest.approx(0.25)
    assert adjusted[0].close == pytest.approx(400.0)
    assert adjusted[0].adjusted_close == pytest.approx(100.0)
    assert adjusted[1].split_factor == pytest.approx(1.0)
    assert adjusted[1].adjusted_close == pytest.approx(100.0)


def test_multiple_future_splits_accumulate_multiplicatively() -> None:
    bars = (_bar(20, 800.0),)
    actions = (_split(24, 2.0), _split(31, 4.0))
    adjusted = apply_tiingo_split_adjustments(
        bars,
        actions,
        adjustment_anchor_date=date(2020, 8, 31),
    )

    assert adjusted[0].split_factor == pytest.approx(0.125)
    assert adjusted[0].adjusted_close == pytest.approx(100.0)


def test_non_tiingo_bar_is_rejected() -> None:
    bar = _bar(28, 400.0)
    foreign = ProviderDailyBar(
        provider_id="other",
        provider_instrument_id=bar.provider_instrument_id,
        symbol=bar.symbol,
        trade_date=bar.trade_date,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        split_factor=None,
        dividend_cash=0.0,
    )
    with pytest.raises(TiingoResponseError, match="another provider"):
        apply_tiingo_split_adjustments(
            (foreign,),
            (),
            adjustment_anchor_date=date(2020, 8, 31),
        )


def test_invalid_split_factor_is_rejected() -> None:
    with pytest.raises(TiingoResponseError, match="finite and positive"):
        apply_tiingo_split_adjustments(
            (_bar(28, 400.0),),
            (_split(31, 0.0),),
            adjustment_anchor_date=date(2020, 8, 31),
        )
