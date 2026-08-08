"""Narrow discovery helpers for real Massive provider-evaluation cases.

This module is intentionally provider-specific. It discovers exact Massive reference records for a
small evaluation sample without forcing the provider-neutral evaluation harness to enumerate the
entire US equity universe.
"""

from __future__ import annotations

from datetime import date
from typing import cast

from trade_scout.data.contracts import SecurityType
from trade_scout.data.provider import ProviderInstrument
from trade_scout.data.providers.massive import MassiveHttpClient, MassiveIdentityError


def discover_massive_evaluation_instrument(
    client: MassiveHttpClient,
    *,
    symbol: str,
    as_of: date,
) -> ProviderInstrument:
    """Resolve one symbol/date to exactly one stable FIGI-backed Massive common-stock record."""

    matches: dict[str, ProviderInstrument] = {}
    for active in (True, False):
        response = client.get_json(
            "/v3/reference/tickers",
            {
                "ticker": symbol,
                "market": "stocks",
                "type": "CS",
                "date": as_of.isoformat(),
                "active": active,
                "limit": 1000,
            },
        )
        results = response.get("results", [])
        if not isinstance(results, list):
            raise MassiveIdentityError("Massive ticker discovery results must be a list")
        for item in results:
            if not isinstance(item, dict):
                raise MassiveIdentityError("Massive ticker discovery result must be an object")
            record = _evaluation_instrument(cast(dict[str, object], item))
            if record is None or record.symbol != symbol:
                continue
            matches[record.provider_instrument_id] = record

    if len(matches) != 1:
        raise MassiveIdentityError(
            f"expected one stable Massive identity for {symbol} on {as_of}; found {len(matches)}"
        )
    return next(iter(matches.values()))


def _evaluation_instrument(item: dict[str, object]) -> ProviderInstrument | None:
    provider_instrument_id = _string(item.get("composite_figi")) or _string(
        item.get("share_class_figi")
    )
    symbol = _string(item.get("ticker"))
    name = _string(item.get("name"))
    exchange = _string(item.get("primary_exchange"))
    currency = _string(item.get("currency_name")) or _string(item.get("currency_symbol"))
    active = item.get("active")
    if (
        provider_instrument_id is None
        or symbol is None
        or name is None
        or exchange is None
        or currency is None
        or not isinstance(active, bool)
    ):
        return None

    return ProviderInstrument(
        provider_id="massive",
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        name=name,
        exchange=exchange,
        security_type=SecurityType.COMMON_STOCK,
        currency=currency.upper(),
        active=active,
        first_trade_date=_date(item.get("list_date")),
        end_date=_date(item.get("delisted_utc")),
        source_fields={
            key: value
            for key, value in item.items()
            if value is None or isinstance(value, str | int | float | bool)
        },
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MassiveIdentityError("Massive reference date must be a string or null")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise MassiveIdentityError(f"invalid Massive reference date {value!r}") from exc
