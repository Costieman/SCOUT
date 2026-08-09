"""Stooq daily-OHLCV candidate adapter for the free-data-first Phase 1 path.

This adapter is intentionally narrow. It provides bounded, explicitly linked daily
CSV retrieval for evaluation. It does not claim a security master, symbol history,
corporate actions, delisting coverage, or accepted adjustment semantics.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trade_scout.data.contracts import PriceRepresentation
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
from trade_scout.data.raw_store import RawBatchStore

_STOOQ_DOWNLOAD_URL = "https://stooq.com/q/d/l/"


class StooqApiError(RuntimeError):
    """Raised when Stooq cannot satisfy a bounded evaluation request."""


class StooqResponseError(StooqApiError):
    """Raised when a Stooq CSV response violates the expected transport shape."""


class StooqIdentityError(StooqApiError):
    """Raised when a query symbol lacks an explicit Stooq identity link."""


class StooqUnsupportedError(StooqApiError):
    """Raised for capabilities deliberately not claimed by this candidate adapter."""


@dataclass(frozen=True, slots=True)
class StooqInstrumentLink:
    """Explicit mapping from a Stooq query symbol to a stable Trade Scout link ID.

    The provider_instrument_id is an externally reviewed link identity. The adapter
    never promotes the query ticker itself into permanent canonical identity.
    """

    query_symbol: str
    provider_instrument_id: str

    def __post_init__(self) -> None:
        if not self.query_symbol.strip():
            raise ValueError("Stooq query symbol must be non-empty")
        if not self.provider_instrument_id.strip():
            raise ValueError("Stooq provider instrument ID must be non-empty")


class StooqCsvClient(Protocol):
    """Minimal byte-preserving Stooq CSV boundary replaceable by test fixtures."""

    def get_csv(self, *, symbol: str, start: date, end: date) -> bytes: ...


class StooqBytesTransport(Protocol):
    """HTTPS transport boundary for Stooq downloads."""

    def get(self, url: str, *, timeout: float) -> bytes: ...


class StooqUrllibBytesTransport:
    """Standard-library HTTPS transport used by the live candidate client."""

    def get(self, url: str, *, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "text/csv", "User-Agent": "Trade-Scout/0.1"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except HTTPError as exc:
            raise StooqApiError(f"Stooq HTTP error {exc.code}") from exc
        except URLError as exc:
            raise StooqApiError(f"Stooq network error: {exc.reason}") from exc


class StooqHttpClient:
    """Bounded Stooq CSV downloader with optional immutable raw capture."""

    def __init__(
        self,
        *,
        transport: StooqBytesTransport | None = None,
        raw_root: Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Stooq HTTP timeout must be positive")
        self._transport = transport or StooqUrllibBytesTransport()
        self._raw_store = RawBatchStore(raw_root) if raw_root is not None else None
        self._timeout = timeout

    def get_csv(self, *, symbol: str, start: date, end: date) -> bytes:
        parameters = {
            "s": symbol.lower(),
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
            "i": "d",
        }
        payload = self._transport.get(
            f"{_STOOQ_DOWNLOAD_URL}?{urlencode(parameters)}",
            timeout=self._timeout,
        )
        if self._raw_store is not None:
            # The deterministic request scope is preserved in the manifest; the raw
            # bytes themselves remain outside Git. A unique batch ID prevents silent
            # replacement of repeated provider retrievals.
            from datetime import UTC, datetime
            from uuid import uuid4

            self._raw_store.persist(
                payload,
                batch_id=f"stooq-{uuid4().hex}",
                provider_id="stooq",
                endpoint="/q/d/l/",
                retrieval_time=datetime.now(UTC),
                request_parameters=parameters,
                media_type="text/csv",
            )
        return payload


class StooqAdapter:
    """Free-data candidate exposing only bounded, explicitly linked daily OHLCV."""

    provider_id = "stooq"

    def __init__(
        self,
        client: StooqCsvClient,
        *,
        instrument_links: Sequence[StooqInstrumentLink],
    ) -> None:
        links_by_symbol: dict[str, StooqInstrumentLink] = {}
        for link in instrument_links:
            normalized = link.query_symbol.upper()
            if normalized in links_by_symbol:
                raise ValueError(f"duplicate Stooq query symbol {normalized}")
            links_by_symbol[normalized] = StooqInstrumentLink(
                query_symbol=normalized,
                provider_instrument_id=link.provider_instrument_id,
            )
        self._client = client
        self._links_by_symbol = links_by_symbol

    @classmethod
    def from_http(
        cls,
        *,
        instrument_links: Sequence[StooqInstrumentLink],
        raw_root: Path | None = None,
        timeout: float = 30.0,
    ) -> StooqAdapter:
        """Create a no-credential Stooq candidate adapter."""

        return cls(
            StooqHttpClient(raw_root=raw_root, timeout=timeout),
            instrument_links=instrument_links,
        )

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset({DataFamily.DAILY_BARS}),
            adjustment_modes=frozenset({PriceRepresentation.RAW}),
            earliest_daily_bar_date=None,
            supports_delisted=False,
            supports_symbol_history=False,
            timestamp_convention="Stooq daily CSV Date field interpreted as trading-session date",
            known_limitations=(
                "candidate adapter requires explicit provider identity links",
                "instrument enumeration is not implemented or claimed",
                "historical symbol continuity is not implemented or claimed",
                "inactive/delisted coverage is not implemented or claimed",
                "corporate actions are not implemented or claimed",
                "CSV OHLC adjustment semantics remain unaccepted and require empirical characterization",
                "licensing, retention, redistribution, and public-app rights remain an explicit acceptance gate",
            ),
        )

    def health_check(self) -> ProviderHealth:
        if not self._links_by_symbol:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.DEGRADED,
                message="no explicit Stooq instrument link is configured for a bounded health probe",
            )
        symbol = min(self._links_by_symbol)
        today = date.today()
        try:
            self._client.get_csv(symbol=symbol, start=today, end=today)
        except StooqApiError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        del as_of
        raise StooqUnsupportedError(
            "Stooq candidate adapter does not claim a complete instrument master"
        )

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        del provider_instrument_ids
        raise StooqUnsupportedError("Stooq candidate adapter does not claim symbol history")

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        if request.adjustment is not PriceRepresentation.RAW:
            raise StooqUnsupportedError(
                "Stooq adjustment semantics are not accepted; only observed CSV OHLC may be evaluated"
            )
        symbols = self._requested_symbols(request.provider_symbols)
        bars: list[ProviderDailyBar] = []
        for symbol in symbols:
            payload = self._client.get_csv(symbol=symbol, start=request.start, end=request.end)
            link = self._links_by_symbol[symbol]
            for row in _read_stooq_csv(payload):
                trade_date = _parse_date(_required_text(row, "Date"))
                if not request.start <= trade_date <= request.end:
                    raise StooqResponseError(
                        f"Stooq returned {symbol} bar outside requested range: {trade_date}"
                    )
                bars.append(
                    ProviderDailyBar(
                        provider_id=self.provider_id,
                        provider_instrument_id=link.provider_instrument_id,
                        symbol=symbol,
                        trade_date=trade_date,
                        open=_required_float(row, "Open"),
                        high=_required_float(row, "High"),
                        low=_required_float(row, "Low"),
                        close=_required_float(row, "Close"),
                        volume=_required_float(row, "Volume"),
                        split_factor=None,
                        dividend_cash=None,
                    )
                )
        return tuple(
            sorted(
                bars,
                key=lambda bar: (bar.symbol, bar.trade_date, bar.provider_instrument_id),
            )
        )

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        del request
        raise StooqUnsupportedError(
            "Stooq candidate adapter does not claim corporate-action coverage"
        )

    def _requested_symbols(self, symbols: tuple[str, ...] | None) -> tuple[str, ...]:
        if not symbols:
            raise StooqApiError("Stooq candidate adapter requires explicit provider symbols")
        normalized = tuple(symbol.upper() for symbol in symbols)
        for symbol in normalized:
            if symbol not in self._links_by_symbol:
                raise StooqIdentityError(
                    f"Stooq symbol {symbol} has no explicit provider identity link"
                )
        return normalized


def _read_stooq_csv(payload: bytes) -> tuple[Mapping[str, str], ...]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StooqResponseError("Stooq returned non-UTF-8 CSV") from exc
    stripped = text.strip()
    if not stripped or stripped.lower().startswith("no data"):
        return ()
    reader = csv.DictReader(io.StringIO(text))
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise StooqResponseError(
            "Stooq CSV is missing required Date/Open/High/Low/Close/Volume columns"
        )
    rows: list[Mapping[str, str]] = []
    for row in reader:
        rows.append({key: value or "" for key, value in row.items() if key is not None})
    return tuple(rows)


def _required_text(row: Mapping[str, str], field: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise StooqResponseError(f"Stooq CSV field {field} must be non-empty")
    return value


def _required_float(row: Mapping[str, str], field: str) -> float:
    value = _required_text(row, field)
    try:
        parsed = float(value)
    except ValueError as exc:
        raise StooqResponseError(f"Stooq CSV field {field} must be numeric") from exc
    if parsed < 0:
        raise StooqResponseError(f"Stooq CSV field {field} must be non-negative")
    return parsed


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise StooqResponseError(f"invalid Stooq date {value!r}") from exc
