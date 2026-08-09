"""EODHD-specific corporate-action enrichment for provider-neutral adjustment logic."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.provider import ProviderCorporateAction
from trade_scout.data.providers.eodhd import EodhdResponseError


def normalize_eodhd_adjustment_actions(
    actions: Iterable[ProviderCorporateAction],
) -> tuple[ProviderCorporateAction, ...]:
    """Add explicit normalized split/dividend values while preserving original source fields."""

    result: list[ProviderCorporateAction] = []
    for action in actions:
        if action.provider_id != "eodhd":
            raise EodhdResponseError("EODHD adjustment normalization received another provider")
        source_fields = dict(action.source_fields)
        if action.action_type is CorporateActionType.SPLIT:
            source_fields["split_ratio"] = _parse_split_ratio(source_fields.get("split"))
        elif action.action_type is CorporateActionType.CASH_DIVIDEND:
            source_fields["dividend_cash"] = _parse_dividend_cash(source_fields.get("value"))
        result.append(replace(action, source_fields=source_fields))
    return tuple(result)


def _parse_split_ratio(value: object) -> float:
    if not isinstance(value, str):
        raise EodhdResponseError("EODHD split action requires textual split ratio")
    parts = [part.strip() for part in value.split("/")]
    if len(parts) != 2:
        raise EodhdResponseError(f"invalid EODHD split ratio {value!r}")
    try:
        numerator = float(parts[0])
        denominator = float(parts[1])
    except ValueError as exc:
        raise EodhdResponseError(f"invalid EODHD split ratio {value!r}") from exc
    if numerator <= 0 or denominator <= 0:
        raise EodhdResponseError(f"invalid EODHD split ratio {value!r}")
    return numerator / denominator


def _parse_dividend_cash(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise EodhdResponseError("EODHD dividend action requires non-negative numeric value")
    return float(value)
