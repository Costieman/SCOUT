"""Alpha Vantage candidate adapter for Phase 1 provider evaluation.

The adapter deliberately exposes only capabilities that are sufficiently characterized for the
current evaluation. In particular, LISTING_STATUS is used for point-in-time active/delisted universe
reconstruction while permanent identity, corporate actions, and long-history OHLCV remain gated.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from trade_scout.data.contracts import PriceRepresentation, SecurityType
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

_ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


class AlphaVantageApiError(RuntimeError):
    """Raised when Alpha Vantage cannot satisfy a provider request."""


class AlphaVantageResponseError(AlphaVantageApiError):
    """Raised when an Alpha Vantage response cannot be interpreted safely."""


class AlphaVantageCapabilityError(AlphaVantageApiError):
    """Raised when a requested capability is outside the accepted evaluation boundary."""


class BytesTransport(Protocol):
    """Raw-byte HTTP boundary replaceable by deterministic fixtures."""

    def get(self, url: str, *, timeout: float) -> bytes: ...


class RawResponseCapture(Protocol):
    """Optional immutable raw-response sink."""

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
        media_type: str,
    ) -> None: ...


class AlphaVantageCsvClient(Protocol):
    """Minimal CSV client boundary consumed by the adapter."""

    def get_csv(self, parameters: Mapping[str, Primitive]) -> bytes: ...


class UrllibBytesTransport:
    """Small standard-library transport for evaluation calls."""

    def get(self, url: str, *, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "text/csv,application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except HTTPError as exc:
            raise AlphaVantageApiError(f"Alpha Vantage HTTP error {exc.code}") from exc
        except URLError as exc:
            raise AlphaVantageApiError(f"Alpha Vantage network error: {exc.reason}") from exc


class RawStoreCapture:
    """Persist exact provider responses through the immutable raw-zone store."""

    def __init__(self, store: RawBatchStore) -> None:
        self._store = store

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
        media_type: str,
    ) -> None:
        self._store.persist(
            payload,
            batch_id=f"alpha-vantage-{uuid4().hex}",
            provider_id="alpha_vantage",
            endpoint=endpoint,
            retrieval_time=datetime.now(UTC),
            request_parameters=request_parameters,
            media_type=media_type,
        )


class AlphaVantageHttpClient:
    """Authenticated client with optional exact-byte raw capture."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: BytesTransport | None = None,
        raw_capture: RawResponseCapture | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Alpha Vantage API key must be non-empty")
        if timeout <= 0:
            raise ValueError("Alpha Vantage HTTP timeout must be positive")
        self._api_key = api_key
        self._transport = transport or UrllibBytesTransport()
        self._raw_capture = raw_capture
        self._timeout = timeout

    def get_csv(self, parameters: Mapping[str, Primitive]) -> bytes:
        safe_parameters = dict(parameters)
        query = dict(safe_parameters)
        query["apikey"] = self._api_key
        payload = self._transport.get(
            f"{_ALPHA_VANTAGE_URL}?{urlencode(query)}",
            timeout=self._timeout,
        )
        _raise_for_api_message(payload)
        if self._raw_capture is not None:
            self._raw_capture.capture(
                payload,
                endpoint="/query",
                request_parameters=safe_parameters,
                media_type="text/csv",
            )
        return payload


@dataclass(frozen=True, slots=True)
class _ListingRow:
    symbol: str
    name: str
    exchange: str
    asset_type: str
    ipo_date: date | None
    delisting_date: date | None
    status: str


class AlphaVantageAdapter:
    """Evaluation adapter focused on listing status and raw daily OHLCV."""

    provider_id = "alpha_vantage"

    def __init__(
        self,
        client: AlphaVantageCsvClient,
        *,
        allow_full_history: bool = False,
    ) -> None:
        self._client = client
        self._allow_full_history = allow_full_history

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        *,
        raw_root: Path | None = None,
        timeout: float = 30.0,
        allow_full_history: bool = False,
    ) -> AlphaVantageAdapter:
        """Construct the adapter without persisting credentials in project state."""

        raw_capture: RawResponseCapture | None = None
        if raw_root is not None:
            raw_capture = RawStoreCapture(RawBatchStore(raw_root))
        client = AlphaVantageHttpClient(
            api_key,
            raw_capture=raw_capture,
            timeout=timeout,
        )
        return cls(client, allow_full_history=allow_full_history)

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset(
                {
                    DataFamily.INSTRUMENTS,
                    DataFamily.STATUS_DELISTINGS,
                    DataFamily.DAILY_BARS,
                }
            ),
            adjustment_modes=frozenset({PriceRepresentation.RAW}),
            earliest_daily_bar_date=None,
            supports_delisted=True,
            supports_symbol_history=False,
            timestamp_convention="US equity trading-session date from Alpha Vantage CSV output",
            known_limitations=(
                "LISTING_STATUS history begins after 2010-01-01.",
                "LISTING_STATUS provides symbols rather than a documented permanent security "
                "identifier; ticker must not become the canonical Trade Scout identity.",
                "TIME_SERIES_DAILY compact output is limited to the latest approximately 100 "
                "observations; full output is plan-dependent and must be enabled explicitly after "
                "entitlement is verified.",
                "This evaluation adapter does not claim complete symbol-history reconstruction.",
                "Corporate-action retrieval is not accepted through this adapter yet; adjustment "
                "and event coverage require a separate validation gate.",
            ),
        )

    def health_check(self) -> ProviderHealth:
        try:
            rows = self._listing_rows(as_of=None, state="active")
        except AlphaVantageApiError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
            )
        if not rows:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.DEGRADED,
                message="LISTING_STATUS returned no active instruments",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        active_rows = self._listing_rows(as_of=as_of, state="active")
        delisted_rows = self._listing_rows(as_of=as_of, state="delisted")
        rows: dict[tuple[str, str], _ListingRow] = {}
        for row in (*active_rows, *delisted_rows):
            rows[(row.symbol, row.status.lower())] = row
        return tuple(self._to_provider_instrument(row) for row in rows.values())

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        del provider_instrument_ids
        raise AlphaVantageCapabilityError(
            "Alpha Vantage LISTING_STATUS does not by itself provide accepted permanent "
            "symbol history"
        )

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        if request.adjustment is not PriceRepresentation.RAW:
            raise AlphaVantageCapabilityError(
                "Alpha Vantage evaluation adapter currently accepts only raw TIME_SERIES_DAILY bars"
            )
        if not request.provider_symbols:
            raise ValueError("Alpha Vantage daily-bar requests require explicit provider symbols")
        if not self._allow_full_history and request.start < request.end - timedelta(days=180):
            raise AlphaVantageCapabilityError(
                "Requested range exceeds the compact-output evaluation window; verify paid "
                "full-output entitlement before enabling long-history retrieval"
            )

        outputsize = "full" if self._allow_full_history else "compact"
        result: list[ProviderDailyBar] = []
        for symbol in request.provider_symbols:
            payload = self._client.get_csv(
                {
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": outputsize,
                    "datatype": "csv",
                }
            )
            rows = _read_csv_rows(payload)
            if rows and "timestamp" not in rows[0]:
                raise AlphaVantageResponseError("TIME_SERIES_DAILY CSV is missing timestamp column")
            for row in rows:
                trade_date = _parse_required_date(row.get("timestamp"), field="timestamp")
                if request.start <= trade_date <= request.end:
                    result.append(_to_provider_bar(symbol, row, trade_date))
        return tuple(sorted(result, key=lambda bar: (bar.symbol, bar.trade_date)))

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        del request
        raise AlphaVantageCapabilityError(
            "Corporate-action coverage must pass a separate Alpha Vantage validation gate "
            "before use"
        )

    def _listing_rows(self, *, as_of: date | None, state: str) -> tuple[_ListingRow, ...]:
        if state not in {"active", "delisted"}:
            raise ValueError("Alpha Vantage listing state must be active or delisted")
        if as_of is not None and as_of <= date(2010, 1, 1):
            raise AlphaVantageCapabilityError(
                "Alpha Vantage LISTING_STATUS supports historical dates later than 2010-01-01"
            )
        parameters: dict[str, Primitive] = {
            "function": "LISTING_STATUS",
            "state": state,
        }
        if as_of is not None:
            parameters["date"] = as_of.isoformat()
        return tuple(
            _parse_listing_row(row) for row in _read_csv_rows(self._client.get_csv(parameters))
        )

    def _to_provider_instrument(self, row: _ListingRow) -> ProviderInstrument:
        return ProviderInstrument(
            provider_id=self.provider_id,
            provider_instrument_id=_symbol_identity(row.symbol),
            symbol=row.symbol,
            name=row.name,
            exchange=row.exchange,
            security_type=_security_type(row.asset_type),
            currency="USD",
            active=row.status.strip().lower() == "active",
            first_trade_date=row.ipo_date,
            end_date=row.delisting_date,
            source_fields={
                "asset_type": row.asset_type,
                "status": row.status,
                "identity_warning": (
                    "symbol-derived provider ID is not permanent canonical identity"
                ),
            },
        )


def _to_provider_bar(
    symbol: str,
    row: Mapping[str, str],
    trade_date: date,
) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="alpha_vantage",
        provider_instrument_id=_symbol_identity(symbol),
        symbol=symbol,
        trade_date=trade_date,
        open=_parse_required_float(row.get("open"), field="open"),
        high=_parse_required_float(row.get("high"), field="high"),
        low=_parse_required_float(row.get("low"), field="low"),
        close=_parse_required_float(row.get("close"), field="close"),
        volume=_parse_required_float(row.get("volume"), field="volume"),
    )


def _raise_for_api_message(payload: bytes) -> None:
    if not payload.lstrip().startswith(b"{"):
        return
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlphaVantageResponseError(
            "Alpha Vantage returned invalid JSON instead of CSV"
        ) from exc
    if not isinstance(parsed, dict):
        raise AlphaVantageResponseError("Alpha Vantage returned unexpected JSON instead of CSV")
    for key in ("Error Message", "Information", "Note"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            raise AlphaVantageApiError(f"Alpha Vantage {key}: {value.strip()}")
    raise AlphaVantageResponseError("Alpha Vantage returned JSON where CSV was expected")


def _read_csv_rows(payload: bytes) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AlphaVantageResponseError("Alpha Vantage CSV is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    return [dict(row) for row in reader if any((value or "").strip() for value in row.values())]


def _parse_listing_row(row: Mapping[str, str]) -> _ListingRow:
    return _ListingRow(
        symbol=_required_text(row.get("symbol"), field="symbol"),
        name=_required_text(row.get("name"), field="name"),
        exchange=_required_text(row.get("exchange"), field="exchange"),
        asset_type=_required_text(row.get("assetType"), field="assetType"),
        ipo_date=_parse_optional_date(row.get("ipoDate")),
        delisting_date=_parse_optional_date(row.get("delistingDate")),
        status=_required_text(row.get("status"), field="status"),
    )


def _security_type(asset_type: str) -> SecurityType:
    normalized = asset_type.strip().lower()
    if normalized in {"stock", "common stock", "common_stock"}:
        return SecurityType.COMMON_STOCK
    if normalized in {"etf", "exchange traded fund", "exchange-traded fund"}:
        return SecurityType.ETF
    return SecurityType.OTHER


def _symbol_identity(symbol: str) -> str:
    return f"alpha_vantage:symbol:{symbol}"


def _required_text(value: str | None, *, field: str) -> str:
    if value is None or not value.strip():
        raise AlphaVantageResponseError(f"Alpha Vantage response is missing required field {field}")
    return value.strip()


def _parse_optional_date(value: str | None) -> date | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in {"null", "none", "n/a"}:
        return None
    try:
        return date.fromisoformat(stripped)
    except ValueError as exc:
        raise AlphaVantageResponseError(f"Invalid Alpha Vantage date: {stripped}") from exc


def _parse_required_date(value: str | None, *, field: str) -> date:
    parsed = _parse_optional_date(value)
    if parsed is None:
        raise AlphaVantageResponseError(f"Alpha Vantage response is missing required date {field}")
    return parsed


def _parse_required_float(value: str | None, *, field: str) -> float:
    if value is None or not value.strip():
        raise AlphaVantageResponseError(
            f"Alpha Vantage response is missing required numeric field {field}"
        )
    try:
        return float(value)
    except ValueError as exc:
        raise AlphaVantageResponseError(
            f"Invalid Alpha Vantage numeric value for {field}: {value}"
        ) from exc
