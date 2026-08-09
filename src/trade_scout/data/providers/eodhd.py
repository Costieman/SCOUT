"""EODHD candidate adapter for the Phase 1 historical-data foundation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
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

_EODHD_BASE_URL = "https://eodhd.com"
_EODHD_HOST = "eodhd.com"


class EodhdApiError(RuntimeError):
    """Raised when EODHD cannot satisfy an evaluation request."""


class EodhdResponseError(EodhdApiError):
    """Raised when an EODHD response violates the required adapter shape."""


class EodhdIdentityError(EodhdApiError):
    """Raised when a ticker has no explicitly approved provider identity link."""


class EodhdUnsupportedError(EodhdApiError):
    """Raised for EODHD capabilities deliberately excluded from this adapter version."""


@dataclass(frozen=True, slots=True)
class EodhdInstrumentLink:
    """Explicit query-symbol to EODHD provider-identity mapping."""

    query_symbol: str
    provider_instrument_id: str

    def __post_init__(self) -> None:
        if not self.query_symbol.strip():
            raise ValueError("EODHD query symbol must be non-empty")
        if not self.provider_instrument_id.strip():
            raise ValueError("EODHD provider instrument ID must be non-empty")


class EodhdJsonClient(Protocol):
    """Minimal JSON boundary replaced by deterministic fixtures in CI."""

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> object: ...


class EodhdBytesTransport(Protocol):
    """Raw HTTPS transport used by the authenticated client."""

    def get(self, url: str, *, timeout: float) -> bytes: ...


class EodhdRawResponseCapture(Protocol):
    """Optional sink receiving exact provider bytes before JSON decoding."""

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None: ...


class EodhdUrllibBytesTransport:
    """Standard-library EODHD HTTPS transport."""

    def get(self, url: str, *, timeout: float) -> bytes:
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
                return bytes(response.read())
        except HTTPError as exc:
            raise EodhdApiError(f"EODHD HTTP error {exc.code}") from exc
        except URLError as exc:
            raise EodhdApiError(f"EODHD network error: {exc.reason}") from exc


class EodhdRawStoreCapture:
    """Persist exact EODHD response bytes without storing the API token in manifests."""

    def __init__(self, store: RawBatchStore) -> None:
        self._store = store

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None:
        self._store.persist(
            payload,
            batch_id=f"eodhd-{uuid4().hex}",
            provider_id="eodhd",
            endpoint=endpoint,
            retrieval_time=datetime.now(UTC),
            request_parameters=request_parameters,
            media_type="application/json",
        )


class EodhdHttpClient:
    """EODHD JSON client whose raw manifests exclude the API token."""

    def __init__(
        self,
        api_token: str,
        *,
        transport: EodhdBytesTransport | None = None,
        raw_capture: EodhdRawResponseCapture | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_token.strip():
            raise ValueError("EODHD API token must be non-empty")
        if timeout <= 0:
            raise ValueError("EODHD HTTP timeout must be positive")
        self._api_token = api_token
        self._transport = transport or EodhdUrllibBytesTransport()
        self._raw_capture = raw_capture
        self._timeout = timeout

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> object:
        path = _validate_endpoint(endpoint)
        safe_parameters = dict(parameters or {})
        wire_parameters = {**safe_parameters, "api_token": self._api_token, "fmt": "json"}
        url = f"{_EODHD_BASE_URL}{path}?{urlencode(wire_parameters)}"
        payload = self._transport.get(url, timeout=self._timeout)
        if self._raw_capture is not None:
            self._raw_capture.capture(
                payload,
                endpoint=path,
                request_parameters=safe_parameters,
            )
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EodhdResponseError("EODHD returned invalid JSON") from exc
        if isinstance(parsed, dict):
            error = parsed.get("error") or parsed.get("message")
            if isinstance(error, str) and error.strip():
                raise EodhdApiError(f"EODHD API error: {error.strip()}")
        return parsed


class EodhdAdapter:
    """Conservative EODHD evaluation adapter behind the provider-neutral boundary."""

    provider_id = "eodhd"

    def __init__(
        self,
        client: EodhdJsonClient,
        *,
        instrument_links: Sequence[EodhdInstrumentLink] = (),
        exchange_code: str = "US",
    ) -> None:
        if not exchange_code.strip():
            raise ValueError("EODHD exchange code must be non-empty")
        self._client = client
        self._exchange_code = exchange_code.upper()
        self._links_by_symbol: dict[str, EodhdInstrumentLink] = {}
        for link in instrument_links:
            symbol = link.query_symbol.upper()
            if symbol in self._links_by_symbol:
                raise ValueError(f"duplicate EODHD query symbol {symbol}")
            self._links_by_symbol[symbol] = EodhdInstrumentLink(
                query_symbol=symbol,
                provider_instrument_id=link.provider_instrument_id,
            )

    @classmethod
    def from_api_token(
        cls,
        api_token: str,
        *,
        instrument_links: Sequence[EodhdInstrumentLink] = (),
        exchange_code: str = "US",
        raw_root: Path | None = None,
        timeout: float = 30.0,
    ) -> EodhdAdapter:
        raw_capture: EodhdRawResponseCapture | None = None
        if raw_root is not None:
            raw_capture = EodhdRawStoreCapture(RawBatchStore(raw_root))
        return cls(
            EodhdHttpClient(api_token, raw_capture=raw_capture, timeout=timeout),
            instrument_links=instrument_links,
            exchange_code=exchange_code,
        )

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset(
                {
                    DataFamily.INSTRUMENTS,
                    DataFamily.STATUS_DELISTINGS,
                    DataFamily.DAILY_BARS,
                    DataFamily.CORPORATE_ACTIONS,
                }
            ),
            adjustment_modes=frozenset({PriceRepresentation.RAW}),
            earliest_daily_bar_date=None,
            supports_delisted=True,
            supports_symbol_history=False,
            timestamp_convention="EODHD EOD date interpreted as the market trading-session date",
            known_limitations=(
                "exchange symbol lists are current/delisted inventories, not historical as-of snapshots",
                "ISIN is used as provider identity where available; rows without ISIN remain provisional",
                "the US symbol-change endpoint starts in 2022 and is not accepted as complete history",
                "adjusted_close is not exposed as split-adjusted OHLC because the adapter lacks a complete "
                "split-only OHLC representation",
                "paid entitlement is required for the long history needed by Phase 1",
                "personal-use storage rights end with the active subscription under current public terms",
            ),
        )

    def health_check(self) -> ProviderHealth:
        try:
            rows = self._instrument_rows(delisted=False)
        except EodhdApiError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
            )
        if not rows:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.DEGRADED,
                message="EODHD exchange symbol list returned no active rows",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        if as_of is not None:
            raise EodhdUnsupportedError(
                "EODHD current/delisted symbol inventories must not be back-projected as historical as-of data"
            )
        result = [
            self._to_instrument(row, active=True) for row in self._instrument_rows(delisted=False)
        ]
        result.extend(
            self._to_instrument(row, active=False) for row in self._instrument_rows(delisted=True)
        )
        unique: dict[tuple[str, bool], ProviderInstrument] = {}
        for instrument in result:
            unique[(instrument.provider_instrument_id, instrument.active)] = instrument
        return tuple(sorted(unique.values(), key=lambda item: (item.symbol, not item.active)))

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        del provider_instrument_ids
        raise EodhdUnsupportedError(
            "EODHD symbol-change coverage begins in 2022 and is not accepted as complete symbol history"
        )

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        if request.adjustment is not PriceRepresentation.RAW:
            raise EodhdUnsupportedError(
                "EODHD candidate adapter currently exposes raw OHLCV only; adjusted_close is not "
                "relabelled as split-adjusted OHLC"
            )
        symbols = self._requested_symbols(request.provider_symbols)
        result: list[ProviderDailyBar] = []
        for symbol in symbols:
            response = self._client.get_json(
                f"/api/eod/{quote(symbol, safe='.')}",
                {
                    "from": request.start.isoformat(),
                    "to": request.end.isoformat(),
                    "period": "d",
                },
            )
            rows = _require_object_list(response, context="EODHD EOD prices")
            link = self._links_by_symbol[symbol]
            for row in rows:
                trade_date = _parse_date(_require_string(row, "date"))
                if not request.start <= trade_date <= request.end:
                    raise EodhdResponseError(
                        f"EODHD returned {symbol} bar outside requested date range: {trade_date}"
                    )
                result.append(
                    ProviderDailyBar(
                        provider_id=self.provider_id,
                        provider_instrument_id=link.provider_instrument_id,
                        symbol=symbol,
                        trade_date=trade_date,
                        open=_require_number(row, "open"),
                        high=_require_number(row, "high"),
                        low=_require_number(row, "low"),
                        close=_require_number(row, "close"),
                        volume=_require_number(row, "volume"),
                    )
                )
        return tuple(sorted(result, key=lambda item: (item.symbol, item.trade_date)))

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        symbols = self._requested_symbols(request.provider_symbols)
        result: list[ProviderCorporateAction] = []
        for symbol in symbols:
            link = self._links_by_symbol[symbol]
            for endpoint, action_type in (
                ("splits", CorporateActionType.SPLIT),
                ("div", CorporateActionType.CASH_DIVIDEND),
            ):
                response = self._client.get_json(
                    f"/api/{endpoint}/{quote(symbol, safe='.')}",
                    {"from": request.start.isoformat(), "to": request.end.isoformat()},
                )
                rows = _require_object_list(response, context=f"EODHD {endpoint}")
                for row in rows:
                    effective_date = _parse_date(_require_string(row, "date"))
                    if not request.start <= effective_date <= request.end:
                        raise EodhdResponseError(
                            f"EODHD returned {symbol} corporate action outside requested date range"
                        )
                    result.append(
                        ProviderCorporateAction(
                            provider_id=self.provider_id,
                            provider_instrument_id=link.provider_instrument_id,
                            source_event_id=None,
                            action_type=action_type,
                            effective_date=effective_date,
                            source_fields=_primitive_source_fields(row),
                        )
                    )
        return tuple(
            sorted(
                result,
                key=lambda item: (
                    item.effective_date,
                    item.provider_instrument_id,
                    str(item.action_type),
                ),
            )
        )

    def _requested_symbols(self, symbols: tuple[str, ...] | None) -> tuple[str, ...]:
        if not symbols:
            raise EodhdApiError("EODHD daily/action requests require explicit provider symbols")
        normalized = tuple(symbol.upper() for symbol in symbols)
        for symbol in normalized:
            if symbol not in self._links_by_symbol:
                raise EodhdIdentityError(
                    f"EODHD symbol {symbol} has no explicit provider identity link"
                )
        return normalized

    def _instrument_rows(self, *, delisted: bool) -> tuple[Mapping[str, object], ...]:
        response = self._client.get_json(
            f"/api/exchange-symbol-list/{quote(self._exchange_code, safe='')}",
            {"delisted": 1 if delisted else 0},
        )
        return _require_object_list(response, context="EODHD exchange symbol list")

    def _to_instrument(self, row: Mapping[str, object], *, active: bool) -> ProviderInstrument:
        code = _require_string(row, "Code")
        exchange = _optional_string(row, "Exchange") or self._exchange_code
        isin = _optional_string(row, "Isin")
        provider_instrument_id = (
            f"eodhd:isin:{isin}" if isin else f"eodhd:symbol:{code}.{self._exchange_code}"
        )
        return ProviderInstrument(
            provider_id=self.provider_id,
            provider_instrument_id=provider_instrument_id,
            symbol=f"{code}.{self._exchange_code}",
            name=_optional_string(row, "Name") or "",
            exchange=exchange,
            security_type=_security_type(_optional_string(row, "Type")),
            currency=_optional_string(row, "Currency") or "USD",
            active=active,
            first_trade_date=None,
            end_date=None,
            source_fields={
                **_primitive_source_fields(row),
                "identity_quality": "ISIN" if isin else "PROVISIONAL_SYMBOL",
                "identity_warning": (
                    None if isin else "symbol-derived provider ID is not permanent canonical identity"
                ),
            },
        )


def _validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != _EODHD_HOST:
            raise EodhdApiError("refusing EODHD URL on an unexpected host")
        if parsed.query or parsed.fragment:
            raise EodhdApiError("EODHD endpoint must not contain embedded query or fragment data")
        return parsed.path
    if not endpoint.startswith("/") or "?" in endpoint or "#" in endpoint:
        raise EodhdApiError("EODHD endpoint must be a query-free absolute API path")
    return endpoint


def _require_object_list(value: object, *, context: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise EodhdResponseError(f"{context} response must be a list")
    rows: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise EodhdResponseError(f"{context} row must be an object")
        rows.append(cast(Mapping[str, object], item))
    return tuple(rows)


def _primitive_source_fields(item: Mapping[str, object]) -> Mapping[str, Primitive]:
    return {
        key: value
        for key, value in item.items()
        if value is None or isinstance(value, str | int | float | bool)
    }


def _optional_string(item: Mapping[str, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EodhdResponseError(f"EODHD field {key} must be text when present")
    stripped = value.strip()
    return stripped or None


def _require_string(item: Mapping[str, object], key: str) -> str:
    value = _optional_string(item, key)
    if value is None:
        raise EodhdResponseError(f"EODHD field {key} must be non-empty text")
    return value


def _require_number(item: Mapping[str, object], key: str) -> float:
    value = item.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise EodhdResponseError(f"EODHD field {key} must be numeric")
    return float(value)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise EodhdResponseError(f"invalid EODHD date {value!r}") from exc


def _security_type(value: str | None) -> SecurityType:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "common_stock": SecurityType.COMMON_STOCK,
        "stock": SecurityType.COMMON_STOCK,
        "preferred_stock": SecurityType.PREFERRED_STOCK,
        "etf": SecurityType.ETF,
        "etn": SecurityType.ETN,
        "closed_end_fund": SecurityType.CLOSED_END_FUND,
        "warrant": SecurityType.WARRANT,
        "right": SecurityType.RIGHT,
    }
    return mapping.get(normalized, SecurityType.OTHER)
