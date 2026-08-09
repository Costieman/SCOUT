from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.provider import ProviderCorporateAction, ProviderDailyBar
from trade_scout.data.provider_adjustments import (
    ProviderAdjustmentError,
    materialize_split_adjusted_bars,
)
from trade_scout.data.providers.eodhd import EodhdResponseError
from trade_scout.data.providers.eodhd_adjustments import normalize_eodhd_adjustment_actions


def _bar(day: int, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="eodhd",
        provider_instrument_id="eodhd:isin:US0378331005",
        symbol="AAPL.US",
        trade_date=date(2020, 8, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def _action(
    action_type: CorporateActionType,
    day: int,
    source_fields: dict[str, str | int | float | bool | None],
) -> ProviderCorporateAction:
    return ProviderCorporateAction(
        provider_id="eodhd",
        provider_instrument_id="eodhd:isin:US0378331005",
        source_event_id=None,
        action_type=action_type,
        effective_date=date(2020, 8, day),
        source_fields=source_fields,
    )


def test_split_factor_applies_only_to_sessions_before_effective_date() -> None:
    actions = normalize_eodhd_adjustment_actions(
        (_action(CorporateActionType.SPLIT, 31, {"split": "4.000000/1.000000"}),)
    )

    result = materialize_split_adjusted_bars(
        (_bar(28, 400.0), _bar(31, 100.0)),
        actions,
        corporate_action_coverage_complete=True,
    )

    assert result[0].split_factor == 0.25
    assert result[0].adjusted_close == 100.0
    assert result[1].split_factor == 1.0
    assert result[1].adjusted_close == 100.0


def test_multiple_future_splits_compound_deterministically() -> None:
    bars = (
        ProviderDailyBar(
            provider_id="fixture",
            provider_instrument_id="fixture:ABC",
            symbol="ABC",
            trade_date=date(2010, 1, 4),
            open=800.0,
            high=800.0,
            low=800.0,
            close=800.0,
            volume=100.0,
        ),
    )
    actions = (
        ProviderCorporateAction(
            provider_id="fixture",
            provider_instrument_id="fixture:ABC",
            source_event_id="split-1",
            action_type=CorporateActionType.SPLIT,
            effective_date=date(2012, 1, 3),
            source_fields={"split_ratio": 2.0},
        ),
        ProviderCorporateAction(
            provider_id="fixture",
            provider_instrument_id="fixture:ABC",
            source_event_id="split-2",
            action_type=CorporateActionType.SPLIT,
            effective_date=date(2014, 1, 2),
            source_fields={"split_ratio": 4.0},
        ),
    )

    result = materialize_split_adjusted_bars(
        bars,
        actions,
        corporate_action_coverage_complete=True,
    )

    assert result[0].split_factor == 0.125
    assert result[0].adjusted_close == 100.0


def test_dividend_cash_is_zero_only_with_explicit_complete_action_coverage() -> None:
    with pytest.raises(ProviderAdjustmentError, match="coverage must be explicitly complete"):
        materialize_split_adjusted_bars(
            (_bar(28, 100.0),),
            (),
            corporate_action_coverage_complete=False,
        )

    result = materialize_split_adjusted_bars(
        (_bar(28, 100.0),),
        (),
        corporate_action_coverage_complete=True,
    )
    assert result[0].dividend_cash == 0.0


def test_eodhd_dividend_value_becomes_explicit_event_date_cash() -> None:
    actions = normalize_eodhd_adjustment_actions(
        (_action(CorporateActionType.CASH_DIVIDEND, 28, {"value": 0.82}),)
    )

    result = materialize_split_adjusted_bars(
        (_bar(28, 100.0), _bar(31, 101.0)),
        actions,
        corporate_action_coverage_complete=True,
    )

    assert result[0].dividend_cash == 0.82
    assert result[1].dividend_cash == 0.0


def test_invalid_eodhd_split_ratio_fails_visibly() -> None:
    with pytest.raises(EodhdResponseError, match="invalid EODHD split ratio"):
        normalize_eodhd_adjustment_actions(
            (_action(CorporateActionType.SPLIT, 31, {"split": "not-a-ratio"}),)
        )


def test_actions_for_unknown_provider_identity_are_rejected() -> None:
    action = ProviderCorporateAction(
        provider_id="eodhd",
        provider_instrument_id="eodhd:isin:OTHER",
        source_event_id=None,
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2020, 8, 31),
        source_fields={"split_ratio": 4.0},
    )

    with pytest.raises(ProviderAdjustmentError, match="absent from the bar scope"):
        materialize_split_adjusted_bars(
            (_bar(28, 400.0),),
            (action,),
            corporate_action_coverage_complete=True,
        )
