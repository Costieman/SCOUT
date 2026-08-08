"""Tiingo EOD candidate adapter for independent secondary validation."""

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

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation
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

_TIINGO_BASE_URL = "https://api.tiingo.com"
_TIINGO_HOST = "api.tiingo.com"


class TiingoApiError(RuntimeError):
    """Raised when Tiingo cannot satisfy a secondary-validation request."""


class TiingoResponseError(TiingoApiError):
    """Raised when a Tiingo response violates the adapter's required shape."""


class TiingoIdentityError(TiingoApiError):
    """Raised when a requested ticker lacks an explicit stable Tiingo identity link."""


class TiingoUnsupportedError(TiingoApiError):
    """Raised for Tiingo capabilities deliberately excluded from this adapter version."""


@dataclass(frozen=True, slots=True)
class TiingoInstrumentLink:
    """Explicit mapping from a query ticker to a stable Tiingo-side identity."""

    query_symbol: str
    provider_instrument_id: str

    def __post_init__(self) -> None:
        if not self.query_symbol.strip():
            raise ValueError("Tiingo query symbol must be non-empty")
        if not self.provider_instrument_id.strip():
            raise ValueError("Tiingo provider instrument ID must be non-empty")


class TiingoJsonClient(Protocol):
    """Minimal JSON boundary used by the adapter and replaced by fixtures in tests."""

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> object: ...


class TiingoBytesTransport(Protocol):
    """Raw HTTPS transport keeping authentication outside the request URL."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes: ...


class TiingoRawResponseCapture(Protocol):
    """Optional sink receiving exact response bytes before JSON decoding."""

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None: ...


class TiingoUrllibBytesTransport:
    """Standard-library Tiingo HTTPS transport."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        request = Request(url, headers=dict(headers))
        try:
            with urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except HTTPError as exc:
            raise TiingoApiError(f"Tiingo HTTP error {exc.code}") from exc
        except URLError as exc:
            raise TiingoApiError(f"Tiingo network error: {exc.reason}") from exc


class TiingoRawStoreCapture:
    """Persist exact Tiingo response bytes through the immutable raw-zone store."""

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
            batch_id=f"tiingo-{uuid4().hex}",
            provider_id="tiingo",
            endpoint=endpoint,
            retrieval_time=datetime.now(UTC),
            request_parameters=request_parameters,
            media_type="application/json",
        )


class TiingoHttpClient:
    """Authenticated Tiingo JSON client with optional exact-byte raw capture."""

    def __init__(
        self,
        api_token: str,
        *,
        transport: TiingoBytesTransport | None = None,
        raw_capture: TiingoRawResponseCapture | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_token.strip():
            raise ValueError("Tiingo API token must be non-empty")
        if timeout <= 0:
            raise ValueError("Tiingo HTTP timeout must be positive")
        self._api_token = api_token
        self._transport = transport or TiingoUrllibBytesTransport()
        self._raw_capture = raw_capture
        self._timeout = timeout

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> object:
        path = _validate_endpoint(endpoint)
        safe_parameters = dict(parameters or {})
        query = urlencode(safe_parameters)
        url = f"{_TIINGO_BASE_URL}{path}"
        if query:
            url = f"{url}?{query}"
        payload = self._transport.get(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Token {self._api_token}",
            },
            timeout=self._timeout,
        )

        if self._raw_capture is not None:
            self._raw_capture.capture(
                payload,
                endpoint=path,
                request_parameters=safe_parameters,
            )

        try:
            return json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TiingoResponseError("Tiingo returned invalid JSON") from exc


class TiingoAdapter:
    """Explicitly linked Tiingo EOD adapter used as independent validation evidence."""

    provider_id = "tiingo"

    def __init__(
        self,
        client: TiingoJsonClient,
        *,
        instrument_links: Sequence[TiingoInstrumentLink],
    ) -> None:
        links_by_symbol: dict[str, TiingoInstrumentLink] = {}
        for link in instrument_links:
            normalized_symbol = link.query_symbol.upper()
            if normalized_symbol in links_by_symbol:
                raise ValueError(f"duplicate Tiingo query symbol {normalized_symbol}")
            links_by_symbol[normalized_symbol] = TiingoInstrumentLink(
                query_symbol=normalized_symbol,
                provider_instrument_id=link.provider_instrument_id,
            )
        self._client = client
        self._links_by_symbol = links_by_symbol

    @classmethod
    def from_api_token(
        cls,
        api_token: str,
        *,
        instrument_links: Sequence[TiingoInstrumentLink],
        raw_root: Path | None = None,
        timeout: float = 30.0,
    ) -> TiingoAdapter:
        """Create the adapter without persisting the Tiingo token in project state."""

        raw_capture: TiingoRawResponseCapture | None = None
        if raw_root is not None:
            raw_capture = TiingoRawStoreCapture(RawBatchStore(raw_root))
        return cls(
            TiingoHttpClient(
                api_token,
                raw_capture=raw_capture,
                timeout=timeout,
            ),
            instrument_links=instrument_links,
        )

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset(
                {
                    DataFamily.DAILY_BARS,
                    DataFamily.CORPORATE_ACTIONS,
                }
            ),
            adjustment_modes=frozenset({PriceRepresentation.RAW}),
            earliest_daily_bar_date=None,
            supports_delisted=True,
            supports_symbol_history=False,
            timestamp_convention="Tiingo EOD ISO date/datetime interpreted as the trading date",
            known_limitations=(
                "full security-master enumeration is not implemented in this secondary adapter",
                "historical symbol continuity is not implemented",
                "delisted support is limited by Tiingo symbology and recycled-ticker coverage",
                "Tiingo adjOHLC includes dividend adjustments and is not exposed as split-adjusted",
                "EOD splitFactor cannot distinguish all detailed corporate-action subtypes",
            ),
        )

    def health_check(self) -> ProviderHealth:
        try:
            response = self._client.get_json("/api/test/")
            if not isinstance(response, dict):
                raise TiingoResponseError("Tiingo health response must be an object")
        except TiingoApiError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        del as_of
        raise TiingoUnsupportedError(
            "Tiingo secondary adapter requires explicit stable identity links; "
            "full instrument enumeration is not implemented"
        )

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        del provider_instrument_ids
        raise TiingoUnsupportedError("Tiingo symbol history is not implemented")

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        if request.adjustment is not PriceRepresentation.RAW:
            raise TiingoUnsupportedError(
                "Tiingo adjusted OHLC includes dividends and cannot be labeled split-adjusted"
            )
        symbols = self._requested_symbols(request.provider_symbols)
        result: list[ProviderDailyBar] = []
        for symbol in symbols:
            link = self._links_by_symbol[symbol]
            for row in self._price_rows(symbol, request.start, request.end):
                trade_date = _parse_date(_require_string(row, "date"))
                if not request.start <= trade_date <= request.end:
                    raise TiingoResponseError(
                        f"Tiingo returned {symbol} bar outside requested date range: {trade_date}"
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
                        split_factor=_require_number(row, "splitFactor"),
                        dividend_cash=_require_number(row, "divCash"),
                        adjusted_open=None,
                        adjusted_high=None,
                        adjusted_low=None,
                        adjusted_close=None,
                    )
                )
        return tuple(
            sorted(
                result,
                key=lambda bar: (
                    bar.symbol,
                    bar.trade_date,
                    bar.provider_instrument_id,
                ),
            )
        )

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        symbols = self._requested_symbols(request.provider_symbols)
        result: list[ProviderCorporateAction] = []
        for symbol in symbols:
            link = self._links_by_symbol[symbol]
            for row in self._price_rows(symbol, request.start, request.end):
                event_date = _parse_date(_require_string(row, "date"))
                if not request.start <= event_date <= request.end:
                    continue
                split_factor = _require_number(row, "splitFactor")
                dividend_cash = _require_number(row, "divCash")
                source_fields = _primitive_source_fields(row)
                if split_factor != 1.0:
                    result.append(
                        ProviderCorporateAction(
                            provider_id=self.provider_id,
                            provider_instrument_id=link.provider_instrument_id,
                            source_event_id=None,
                            action_type=CorporateActionType.SPLIT,
                            effective_date=event_date,
                            source_fields=source_fields,
                        )
                    )
                if dividend_cash != 0.0:
                    result.append(
                        ProviderCorporateAction(
                            provider_id=self.provider_id,
                            provider_instrument_id=link.provider_instrument_id,
                            source_event_id=None,
                            action_type=CorporateActionType.CASH_DIVIDEND,
                            effective_date=event_date,
                            source_fields=source_fields,
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

    def _requested_symbols(self, symbols: tuple[str, ...] | None) -> tuple[str, ...]:
        if not symbols:
            raise TiingoApiError("Tiingo secondary adapter requires explicit provider symbols")
        normalized = tuple(symbol.upper() for symbol in symbols)
        for symbol in normalized:
            if symbol not in self._links_by_symbol:
                raise TiingoIdentityError(
                    f"Tiingo symbol {symbol} has no explicit stable provider identity link"
                )
        return normalized

    def _price_rows(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> tuple[Mapping[str, object], ...]:
        endpoint = f"/tiingo/daily/{quote(symbol, safe='')}/prices"
        response = self._client.get_json(
            endpoint,
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "resampleFreq": "daily",
            },
        )
        if not isinstance(response, list):
            raise TiingoResponseError("Tiingo EOD prices response must be a list")
        rows: list[Mapping[str, object]] = []
        for item in response:
            if not isinstance(item, dict):
                raise TiingoResponseError("Tiingo EOD price row must be an object")
            rows.append(cast(Mapping[str, object], item))
        return tuple(rows)


def _validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != _TIINGO_HOST:
            raise TiingoApiError("refusing Tiingo URL on an unexpected host")
        if parsed.query or parsed.fragment:
            raise TiingoApiError("Tiingo endpoint must not contain embedded query or fragment data")
        return parsed.path
    if not endpoint.startswith("/") or "?" in endpoint or "#" in endpoint:
        raise TiingoApiError("Tiingo endpoint must be a query-free absolute API path")
    return endpoint


def _primitive_source_fields(item: Mapping[str, object]) -> Mapping[str, Primitive]:
    return {
        key: value
        for key, value in item.items()
        if value is None or isinstance(value, str | int | float | bool)
    }


def _require_string(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise TiingoResponseError(f"Tiingo field {key} must be a string")
    return value


def _require_number(item: Mapping[str, object], key: str) -> float:
    value = item.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TiingoResponseError(f"Tiingo field {key} must be numeric")
    return float(value)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise TiingoResponseError(f"invalid Tiingo date {value!r}") from exc
