"""Candidate Massive Stocks REST adapter for Phase 1 provider evaluation.

This module maps documented Massive REST responses into provider-neutral Trade Scout staging
contracts. It is an evaluation adapter, not an accepted canonical-provider declaration.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation, SecurityType
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    DataFamily,
    ProviderCapabilities,
    ProviderCorporateAction,
    ProviderDailyBar,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderInstrument,
    ProviderSymbolHistory,
)
from trade_scout.data.raw_store import Primitive, RawBatchStore

_MASSIVE_BASE_URL = "https://api.massive.com"
_MASSIVE_HOST = "api.massive.com"


class MassiveApiError(RuntimeError):
    """Raised when the Massive API cannot satisfy a provider request."""


class MassiveResponseError(MassiveApiError):
    """Raised when a Massive response violates the documented shape required by the adapter."""


class MassiveIdentityError(MassiveApiError):
    """Raised when a ticker cannot be linked unambiguously to a stable Massive identifier."""


class MassiveJsonClient(Protocol):
    """Minimal JSON boundary used by the adapter and replaced by fixtures in tests."""

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> Mapping[str, object]: ...


class BytesTransport(Protocol):
    """Raw HTTP byte transport used by the concrete Massive client."""

    def get(self, url: str, *, timeout: float) -> bytes: ...


class RawResponseCapture(Protocol):
    """Optional sink that receives exact response bytes before JSON decoding."""

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None: ...


class UrllibBytesTransport:
    """Small standard-library HTTP transport; credentials are added by MassiveHttpClient."""

    def get(self, url: str, *, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except HTTPError as exc:
            raise MassiveApiError(f"Massive HTTP error {exc.code}") from exc
        except URLError as exc:
            raise MassiveApiError(f"Massive network error: {exc.reason}") from exc


class RawStoreCapture:
    """Persist exact Massive response bytes through the existing immutable raw-zone store."""

    def __init__(
        self,
        store: RawBatchStore,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or (lambda: uuid4().hex)

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None:
        self.store.persist(
            payload,
            batch_id=f"massive-{self.id_factory()}",
            provider_id="massive",
            endpoint=endpoint,
            retrieval_time=self.clock(),
            request_parameters=request_parameters,
            media_type="application/json",
        )


class MassiveHttpClient:
    """Authenticated Massive JSON client with optional exact-byte raw capture."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: BytesTransport | None = None,
        raw_capture: RawResponseCapture | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Massive API key must be non-empty")
        if timeout <= 0:
            raise ValueError("Massive HTTP timeout must be positive")
        self._api_key = api_key
        self._transport = transport or UrllibBytesTransport()
        self._raw_capture = raw_capture
        self._timeout = timeout

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> Mapping[str, object]:
        path, safe_parameters = _normalize_endpoint_request(endpoint, parameters or {})
        query_parameters = dict(safe_parameters)
        query_parameters["apiKey"] = self._api_key
        url = f"{_MASSIVE_BASE_URL}{path}?{urlencode(query_parameters)}"
        payload = self._transport.get(url, timeout=self._timeout)

        if self._raw_capture is not None:
            self._raw_capture.capture(
                payload,
                endpoint=path,
                request_parameters=safe_parameters,
            )

        try:
            parsed: object = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MassiveResponseError("Massive returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise MassiveResponseError("Massive response must be a JSON object")
        return cast(Mapping[str, object], parsed)


@dataclass(frozen=True, slots=True)
class _ReferenceIdentity:
    provider_instrument_id: str
    symbol: str
    exchange: str


class MassiveAdapter:
    """Massive candidate adapter implementing the Trade Scout provider protocol."""

    provider_id = "massive"

    def __init__(self, client: MassiveJsonClient) -> None:
        self._client = client

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        *,
        raw_root: Path | None = None,
        timeout: float = 30.0,
    ) -> MassiveAdapter:
        """Create the candidate adapter without persisting credentials in project state."""

        raw_capture: RawResponseCapture | None = None
        if raw_root is not None:
            raw_capture = RawStoreCapture(RawBatchStore(raw_root))
        return cls(
            MassiveHttpClient(
                api_key,
                raw_capture=raw_capture,
                timeout=timeout,
            )
        )

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset(
                {
                    DataFamily.INSTRUMENTS,
                    DataFamily.SYMBOL_HISTORY,
                    DataFamily.DAILY_BARS,
                    DataFamily.CORPORATE_ACTIONS,
                    DataFamily.STATUS_DELISTINGS,
                }
            ),
            adjustment_modes=frozenset(
                {PriceRepresentation.RAW, PriceRepresentation.SPLIT_ADJUSTED}
            ),
            earliest_daily_bar_date=date(2003, 9, 10),
            supports_delisted=True,
            supports_symbol_history=True,
            timestamp_convention="daily aggregate session date from Massive millisecond timestamp",
            known_limitations=(
                "ticker-events symbol history is documented by Massive as experimental",
                "ticker-event exchange uses the first matching reference record within 7 days",
                "instrument admission requires composite FIGI or share-class FIGI",
                "first_trade_date is not supplied by All Tickers and remains unset in this adapter",
                "corporate actions use point-in-time ticker reference lookup for identity",
            ),
        )

    def health_check(self) -> ProviderHealth:
        try:
            response = self._client.get_json(
                "/v3/reference/tickers",
                {"market": "stocks", "type": "CS", "active": True, "limit": 1},
            )
            _require_results_list(response)
        except MassiveApiError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        records: dict[tuple[str, str], ProviderInstrument] = {}
        for active in (True, False):
            parameters: dict[str, Primitive] = {
                "market": "stocks",
                "type": "CS",
                "active": active,
                "limit": 1000,
                "sort": "ticker",
            }
            if as_of is not None:
                parameters["date"] = as_of.isoformat()
            for item in self._iter_results("/v3/reference/tickers", parameters):
                instrument = _provider_instrument(item)
                if instrument is None:
                    continue
                records[(instrument.provider_instrument_id, instrument.symbol)] = instrument
        return tuple(
            sorted(
                records.values(), key=lambda record: (record.symbol, record.provider_instrument_id)
            )
        )

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        if not provider_instrument_ids:
            return ()

        result: list[ProviderSymbolHistory] = []
        for provider_instrument_id in provider_instrument_ids:
            endpoint = f"/vX/reference/tickers/{quote(provider_instrument_id, safe='')}/events"
            response = self._client.get_json(endpoint, {"types": "ticker_change"})
            payload = response.get("results")
            if payload is None:
                continue
            if not isinstance(payload, dict):
                raise MassiveResponseError("ticker-events results must be an object")
            events = payload.get("events", [])
            if not isinstance(events, list):
                raise MassiveResponseError("ticker-events events must be a list")

            dated: list[tuple[date, str]] = []
            for event in events:
                if not isinstance(event, dict) or event.get("type") != "ticker_change":
                    continue
                effective_date = _parse_date(_require_string(event, "date"))
                change = event.get("ticker_change")
                if not isinstance(change, dict):
                    raise MassiveResponseError("ticker_change must be an object")
                symbol = _require_string(change, "ticker")
                dated.append((effective_date, symbol))

            ordered = sorted(set(dated))
            for index, (effective_date, symbol) in enumerate(ordered):
                identity = self._resolve_symbol_history_identity(
                    symbol, effective_date, provider_instrument_id
                )
                if identity.provider_instrument_id != provider_instrument_id:
                    raise MassiveIdentityError(
                        f"symbol-history event {symbol} on {effective_date} resolves to "
                        f"{identity.provider_instrument_id}, expected {provider_instrument_id}"
                    )
                effective_to = (
                    ordered[index + 1][0] - timedelta(days=1) if index + 1 < len(ordered) else None
                )
                result.append(
                    ProviderSymbolHistory(
                        provider_id=self.provider_id,
                        provider_instrument_id=provider_instrument_id,
                        symbol=symbol,
                        exchange=identity.exchange,
                        effective_from=effective_date,
                        effective_to=effective_to,
                    )
                )
        return tuple(
            sorted(
                result,
                key=lambda record: (
                    record.provider_instrument_id,
                    record.effective_from,
                    record.symbol,
                ),
            )
        )

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        if not request.provider_symbols:
            raise MassiveApiError(
                "Massive candidate adapter requires explicit provider_symbols for daily bars"
            )

        result: list[ProviderDailyBar] = []
        for symbol in request.provider_symbols:
            raw = self._aggregate_rows(symbol, request.start, request.end, adjusted=False)
            adjusted = self._aggregate_rows(symbol, request.start, request.end, adjusted=True)
            if set(raw) != set(adjusted):
                raise MassiveResponseError(
                    f"raw and split-adjusted aggregate timestamps differ for {symbol}"
                )
            if not raw:
                continue

            raw_dates = {_timestamp_to_date(timestamp) for timestamp in raw}
            first_date = min(raw_dates)
            last_date = max(raw_dates)
            first_identity = self._resolve_symbol_identity(symbol, first_date)
            last_identity = self._resolve_symbol_identity(symbol, last_date)
            if first_identity.provider_instrument_id != last_identity.provider_instrument_id:
                raise MassiveIdentityError(
                    f"ticker {symbol} maps to different identities inside requested range"
                )
            provider_instrument_id = first_identity.provider_instrument_id
            dividends = self._dividend_cash_by_date(symbol, request.start, request.end)

            for timestamp in sorted(raw):
                raw_row = raw[timestamp]
                adjusted_row = adjusted[timestamp]
                raw_close = _require_number(raw_row, "c")
                adjusted_close = _require_number(adjusted_row, "c")
                if raw_close == 0:
                    raise MassiveResponseError(
                        f"cannot derive split adjustment factor from zero close for {symbol}"
                    )
                trade_date = _timestamp_to_date(timestamp)
                result.append(
                    ProviderDailyBar(
                        provider_id=self.provider_id,
                        provider_instrument_id=provider_instrument_id,
                        symbol=symbol,
                        trade_date=trade_date,
                        open=_require_number(raw_row, "o"),
                        high=_require_number(raw_row, "h"),
                        low=_require_number(raw_row, "l"),
                        close=raw_close,
                        volume=_require_number(raw_row, "v"),
                        split_factor=adjusted_close / raw_close,
                        dividend_cash=dividends.get(trade_date, 0.0),
                        adjusted_open=_require_number(adjusted_row, "o"),
                        adjusted_high=_require_number(adjusted_row, "h"),
                        adjusted_low=_require_number(adjusted_row, "l"),
                        adjusted_close=adjusted_close,
                    )
                )
        return tuple(
            sorted(result, key=lambda bar: (bar.symbol, bar.trade_date, bar.provider_instrument_id))
        )

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        if not request.provider_symbols:
            raise MassiveApiError(
                "Massive candidate adapter requires explicit provider_symbols for corporate actions"
            )

        result: list[ProviderCorporateAction] = []
        for symbol in request.provider_symbols:
            for item in self._iter_results(
                "/stocks/v1/splits",
                {"ticker": symbol, "limit": 5000, "sort": "execution_date.asc"},
            ):
                event_date = _parse_optional_date(item.get("execution_date"))
                if event_date is None or not request.start <= event_date <= request.end:
                    continue
                identity = self._resolve_symbol_identity(symbol, event_date)
                adjustment_type = _optional_string(item.get("adjustment_type"))
                action_type = (
                    CorporateActionType.STOCK_DIVIDEND
                    if adjustment_type == "stock_dividend"
                    else CorporateActionType.SPLIT
                )
                result.append(
                    ProviderCorporateAction(
                        provider_id=self.provider_id,
                        provider_instrument_id=identity.provider_instrument_id,
                        source_event_id=_optional_string(item.get("id")),
                        action_type=action_type,
                        effective_date=event_date,
                        source_fields=_primitive_source_fields(item),
                    )
                )

            for item in self._iter_results(
                "/stocks/v1/dividends",
                {"ticker": symbol, "limit": 5000, "sort": "ex_dividend_date.asc"},
            ):
                event_date = _parse_optional_date(item.get("ex_dividend_date"))
                if event_date is None or not request.start <= event_date <= request.end:
                    continue
                identity = self._resolve_symbol_identity(symbol, event_date)
                result.append(
                    ProviderCorporateAction(
                        provider_id=self.provider_id,
                        provider_instrument_id=identity.provider_instrument_id,
                        source_event_id=_optional_string(item.get("id")),
                        action_type=CorporateActionType.CASH_DIVIDEND,
                        effective_date=event_date,
                        source_fields=_primitive_source_fields(item),
                    )
                )
        return tuple(
            sorted(
                result,
                key=lambda action: (
                    action.effective_date,
                    action.provider_instrument_id,
                    str(action.action_type),
                ),
            )
        )

    def _aggregate_rows(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        adjusted: bool,
    ) -> dict[int, Mapping[str, object]]:
        endpoint = (
            f"/v2/aggs/ticker/{quote(symbol, safe='')}/range/1/day/"
            f"{start.isoformat()}/{end.isoformat()}"
        )
        response = self._client.get_json(
            endpoint,
            {"adjusted": adjusted, "sort": "asc", "limit": 50000},
        )
        rows = _require_results_list(response)
        result: dict[int, Mapping[str, object]] = {}
        for row in rows:
            timestamp = _require_integral_number(row, "t")
            if timestamp in result:
                raise MassiveResponseError(
                    f"duplicate aggregate timestamp {timestamp} for {symbol}"
                )
            result[timestamp] = row
        return result

    def _dividend_cash_by_date(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> dict[date, float]:
        result: dict[date, float] = {}
        for item in self._iter_results(
            "/stocks/v1/dividends",
            {"ticker": symbol, "limit": 5000, "sort": "ex_dividend_date.asc"},
        ):
            event_date = _parse_optional_date(item.get("ex_dividend_date"))
            if event_date is None or not start <= event_date <= end:
                continue
            amount = item.get("cash_amount")
            if amount is None:
                continue
            if not isinstance(amount, int | float) or isinstance(amount, bool):
                raise MassiveResponseError("dividend cash_amount must be numeric")
            result[event_date] = result.get(event_date, 0.0) + float(amount)
        return result

    def _resolve_symbol_history_identity(
        self,
        symbol: str,
        effective_date: date,
        expected_provider_instrument_id: str,
    ) -> _ReferenceIdentity:
        """Resolve ticker-event identity within a bounded reference-data window."""

        for day_offset in range(8):
            lookup_date = effective_date + timedelta(days=day_offset)
            identity = self._try_resolve_symbol_identity(symbol, lookup_date)
            if identity is None:
                continue
            if identity.provider_instrument_id != expected_provider_instrument_id:
                raise MassiveIdentityError(
                    f"symbol-history event {symbol} on {effective_date} resolves to "
                    f"{identity.provider_instrument_id}, expected {expected_provider_instrument_id}"
                )
            return identity
        raise MassiveIdentityError(
            f"could not resolve {symbol} from ticker event {effective_date} within 7 days"
        )

    def _resolve_symbol_identity(self, symbol: str, as_of: date) -> _ReferenceIdentity:
        identity = self._try_resolve_symbol_identity(symbol, as_of)
        if identity is None:
            raise MassiveIdentityError(
                f"expected one stable Massive identity for {symbol} on {as_of}; found 0"
            )
        return identity

    def _try_resolve_symbol_identity(self, symbol: str, as_of: date) -> _ReferenceIdentity | None:
        matches: dict[str, _ReferenceIdentity] = {}
        for active in (True, False):
            response = self._client.get_json(
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
            for item in _require_results_list(response):
                if _optional_string(item.get("ticker")) != symbol:
                    continue
                provider_instrument_id = _stable_provider_id(item)
                exchange = _optional_string(item.get("primary_exchange"))
                if provider_instrument_id is None or exchange is None:
                    continue
                matches[provider_instrument_id] = _ReferenceIdentity(
                    provider_instrument_id=provider_instrument_id,
                    symbol=symbol,
                    exchange=exchange,
                )
        if len(matches) > 1:
            raise MassiveIdentityError(
                f"expected one stable Massive identity for {symbol} on {as_of}; "
                f"found {len(matches)}"
            )
        return next(iter(matches.values())) if matches else None

    def _iter_results(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive],
    ) -> Sequence[Mapping[str, object]]:
        result: list[Mapping[str, object]] = []
        current_endpoint = endpoint
        current_parameters = dict(parameters)
        while True:
            response = self._client.get_json(current_endpoint, current_parameters)
            result.extend(_require_results_list(response))
            next_url = response.get("next_url")
            if next_url is None:
                break
            if not isinstance(next_url, str):
                raise MassiveResponseError("Massive next_url must be a string")
            current_endpoint, current_parameters = _normalize_endpoint_request(next_url, {})
        return tuple(result)


def _provider_instrument(item: Mapping[str, object]) -> ProviderInstrument | None:
    provider_instrument_id = _stable_provider_id(item)
    if provider_instrument_id is None:
        return None
    symbol = _optional_string(item.get("ticker"))
    name = _optional_string(item.get("name"))
    exchange = _optional_string(item.get("primary_exchange"))
    if symbol is None or name is None or exchange is None:
        return None

    currency = _optional_string(item.get("currency_symbol")) or _optional_string(
        item.get("currency_name")
    )
    active = item.get("active")
    if currency is None or not isinstance(active, bool):
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
        first_trade_date=None,
        end_date=_parse_optional_date(item.get("delisted_utc")),
        source_fields=_primitive_source_fields(item),
    )


def _stable_provider_id(item: Mapping[str, object]) -> str | None:
    return _optional_string(item.get("composite_figi")) or _optional_string(
        item.get("share_class_figi")
    )


def _require_results_list(response: Mapping[str, object]) -> list[Mapping[str, object]]:
    results = response.get("results", [])
    if not isinstance(results, list):
        raise MassiveResponseError("Massive results must be a list")
    normalized: list[Mapping[str, object]] = []
    for item in results:
        if not isinstance(item, dict):
            raise MassiveResponseError("Massive result items must be objects")
        normalized.append(cast(Mapping[str, object], item))
    return normalized


def _normalize_endpoint_request(
    endpoint: str,
    parameters: Mapping[str, Primitive],
) -> tuple[str, dict[str, Primitive]]:
    parsed = urlsplit(endpoint)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != _MASSIVE_HOST:
            raise MassiveApiError("refusing to follow a Massive pagination URL on another host")
        path = parsed.path
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        merged: dict[str, Primitive] = {
            key: value for key, value in query_pairs if key.lower() != "apikey"
        }
        merged.update(parameters)
        return path, merged
    if not endpoint.startswith("/") or "?" in endpoint or "#" in endpoint:
        raise MassiveApiError("Massive endpoint must be a query-free absolute API path")
    return endpoint, dict(parameters)


def _primitive_source_fields(item: Mapping[str, object]) -> Mapping[str, Primitive]:
    return {
        key: value
        for key, value in item.items()
        if value is None or isinstance(value, str | int | float | bool)
    }


def _require_string(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise MassiveResponseError(f"Massive field {key} must be a string")
    return value


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _require_number(item: Mapping[str, object], key: str) -> float:
    value = item.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise MassiveResponseError(f"Massive field {key} must be numeric")
    return float(value)


def _require_integral_number(item: Mapping[str, object], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise MassiveResponseError(f"Massive field {key} must be numeric")
    numeric = float(value)
    if not numeric.is_integer():
        raise MassiveResponseError(f"Massive field {key} must be integral")
    return int(numeric)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise MassiveResponseError(f"invalid Massive date {value!r}") from exc


def _parse_optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MassiveResponseError("Massive date field must be a string or null")
    return _parse_date(value)


def _timestamp_to_date(timestamp_ms: int) -> date:
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date()
    except (OverflowError, OSError, ValueError) as exc:
        raise MassiveResponseError(f"invalid Massive aggregate timestamp {timestamp_ms}") from exc
