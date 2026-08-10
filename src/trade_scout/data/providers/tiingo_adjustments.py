"""Tiingo split-event normalization into Trade Scout cumulative split-only factors."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import date
from math import isfinite

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.provider import ProviderCorporateAction, ProviderDailyBar
from trade_scout.data.providers.tiingo import TiingoResponseError


def apply_tiingo_split_adjustments(
    bars: Iterable[ProviderDailyBar],
    actions: Iterable[ProviderCorporateAction],
    *,
    adjustment_anchor_date: date,
) -> tuple[ProviderDailyBar, ...]:
    """Attach split-only factors using complete Tiingo split evidence through an anchor.

    The caller must supply Tiingo split actions covering every split after the earliest
    bar through ``adjustment_anchor_date``. A split effective on date D changes prices
    at D, so bars strictly before D receive the inverse split ratio while bars on/after
    D do not. The result satisfies Trade Scout's contract:
    split-adjusted OHLC = raw OHLC * cumulative split-only multiplier.

    This function deliberately cannot prove that the supplied corporate-action set is
    complete. Backfill orchestration must establish that coverage before promotion.
    """

    frozen_bars = tuple(bars)
    frozen_actions = tuple(actions)
    for bar in frozen_bars:
        if bar.provider_id != "tiingo":
            raise TiingoResponseError("Tiingo adjustment normalization received another provider")
        if bar.trade_date > adjustment_anchor_date:
            raise TiingoResponseError("Tiingo bar lies after split-adjustment anchor")

    split_events: dict[str, list[tuple[date, float]]] = {}
    for action in frozen_actions:
        if action.provider_id != "tiingo":
            raise TiingoResponseError("Tiingo adjustment normalization received another provider")
        if action.action_type is not CorporateActionType.SPLIT:
            continue
        if action.effective_date > adjustment_anchor_date:
            continue
        ratio = _split_ratio(action)
        split_events.setdefault(action.provider_instrument_id, []).append(
            (action.effective_date, ratio)
        )

    result: list[ProviderDailyBar] = []
    for bar in frozen_bars:
        factor = 1.0
        for effective_date, ratio in split_events.get(bar.provider_instrument_id, []):
            if bar.trade_date < effective_date <= adjustment_anchor_date:
                factor /= ratio
        result.append(
            replace(
                bar,
                split_factor=factor,
                adjusted_open=bar.open * factor,
                adjusted_high=bar.high * factor,
                adjusted_low=bar.low * factor,
                adjusted_close=bar.close * factor,
            )
        )
    return tuple(
        sorted(result, key=lambda bar: (bar.provider_instrument_id, bar.trade_date))
    )


def _split_ratio(action: ProviderCorporateAction) -> float:
    value = action.source_fields.get("splitFactor")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TiingoResponseError("Tiingo split action requires numeric splitFactor")
    ratio = float(value)
    if not isfinite(ratio) or ratio <= 0:
        raise TiingoResponseError("Tiingo splitFactor must be finite and positive")
    if ratio == 1.0:
        raise TiingoResponseError("Tiingo split action cannot carry a unit splitFactor")
    return ratio
