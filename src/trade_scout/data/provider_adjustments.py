"""Materialize explicit split-only provider bars from validated corporate-action evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.provider import ProviderCorporateAction, ProviderDailyBar


class ProviderAdjustmentError(ValueError):
    """Raised when provider actions cannot safely support an explicit price adjustment."""


def materialize_split_adjusted_bars(
    bars: Iterable[ProviderDailyBar],
    actions: Iterable[ProviderCorporateAction],
    *,
    corporate_action_coverage_complete: bool,
) -> tuple[ProviderDailyBar, ...]:
    """Attach cumulative split-only factors and event-date dividends to raw provider bars.

    A split ratio is interpreted as ``new shares / old shares``. A bar is adjusted only for splits
    whose effective date is later than that bar's trading date, so the effective-date bar itself is
    treated as post-split. Absence of a dividend is converted to zero only when the caller has
    explicitly established complete corporate-action coverage for the requested scope.
    """

    if not corporate_action_coverage_complete:
        raise ProviderAdjustmentError(
            "corporate-action coverage must be explicitly complete before zero dividends or "
            "split-only factors are materialized"
        )

    materialized_bars = tuple(bars)
    materialized_actions = tuple(actions)
    _validate_scope(materialized_bars, materialized_actions)

    split_events: dict[str, list[tuple[date, float]]] = defaultdict(list)
    dividend_events: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))

    for action in materialized_actions:
        if action.action_type is CorporateActionType.SPLIT:
            split_events[action.provider_instrument_id].append(
                (
                    action.effective_date,
                    _required_positive_number(action.source_fields, "split_ratio"),
                )
            )
        elif action.action_type is CorporateActionType.CASH_DIVIDEND:
            dividend_events[action.provider_instrument_id][action.effective_date] += (
                _required_non_negative_number(action.source_fields, "dividend_cash")
            )

    for events in split_events.values():
        events.sort(key=lambda item: item[0])

    result: list[ProviderDailyBar] = []
    for bar in materialized_bars:
        factor = 1.0
        for effective_date, ratio in split_events.get(bar.provider_instrument_id, []):
            if effective_date > bar.trade_date:
                factor /= ratio
        dividend_cash = dividend_events.get(bar.provider_instrument_id, {}).get(bar.trade_date, 0.0)
        result.append(
            replace(
                bar,
                split_factor=factor,
                dividend_cash=dividend_cash,
                adjusted_open=bar.open * factor,
                adjusted_high=bar.high * factor,
                adjusted_low=bar.low * factor,
                adjusted_close=bar.close * factor,
            )
        )

    return tuple(
        sorted(
            result,
            key=lambda bar: (
                bar.provider_id,
                bar.provider_instrument_id,
                bar.trade_date,
            ),
        )
    )


def _validate_scope(
    bars: tuple[ProviderDailyBar, ...],
    actions: tuple[ProviderCorporateAction, ...],
) -> None:
    provider_ids = {bar.provider_id for bar in bars} | {action.provider_id for action in actions}
    if len(provider_ids) > 1:
        raise ProviderAdjustmentError("split-adjustment materialization cannot mix providers")

    bar_keys = [(bar.provider_instrument_id, bar.trade_date) for bar in bars]
    if len(bar_keys) != len(set(bar_keys)):
        raise ProviderAdjustmentError(
            "provider bars contain duplicate instrument/date observations"
        )

    action_instruments = {action.provider_instrument_id for action in actions}
    bar_instruments = {bar.provider_instrument_id for bar in bars}
    unknown = action_instruments - bar_instruments
    if unknown:
        details = ", ".join(sorted(unknown))
        raise ProviderAdjustmentError(
            f"corporate actions include provider identities absent from the bar scope: {details}"
        )


def _required_positive_number(source_fields: Mapping[str, object], field: str) -> float:
    value = source_fields.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise ProviderAdjustmentError(f"corporate action requires positive numeric {field}")
    return float(value)


def _required_non_negative_number(source_fields: Mapping[str, object], field: str) -> float:
    value = source_fields.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ProviderAdjustmentError(f"corporate action requires non-negative numeric {field}")
    return float(value)
