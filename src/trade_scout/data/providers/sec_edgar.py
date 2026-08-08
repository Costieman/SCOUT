"""SEC EDGAR reference-data adapter for Phase 1 identity evaluation.

SEC EDGAR is treated as an issuer/reference source rather than a market-price provider.
CIK is a filer/entity identifier, not a permanent security identifier, so this adapter never
promotes CIK or ticker directly into Trade Scout canonical security identity.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from trade_scout.data.contracts import SecurityType
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

_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


class SecEdgarApiError(RuntimeError):
    """Raised when SEC EDGAR cannot satisfy a reference-data request."""


class SecEdgarResponseError(SecEdgarApiError):
    """Raised when an SEC response cannot be interpreted safely."""


class SecEdgarCapabilityError(SecEdgarApiError):
    """Raised when a caller requests a capability not accepted from SEC EDGAR."""


class JsonTransport(Protocol):
    """Replaceable byte transport for deterministic tests."""

    def get(self, url: str, *, user_agent: str, timeout: float) -> bytes: ...


class UrllibJsonTransport:
    """Small standard-library transport that declares an SEC-compatible user agent."""

    def get(self, url: str, *, user_agent: str, timeout: float) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": user_agent,
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except HTTPError as exc:
            raise SecEdgarApiError(f"SEC EDGAR HTTP error {exc.code}") from exc
        except URLError as exc:
            raise SecEdgarApiError(f"SEC EDGAR network error: {exc.reason}") from exc


@dataclass(frozen=True, slots=True)
class SecTickerAssociation:
    """Current SEC association between issuer CIK, ticker, exchange, and company name."""

    cik: int
    name: str
    ticker: str
    exchange: str


class SecEdgarClient:
    """Minimal SEC client used by the Phase 1 reference-data adapter."""

    def __init__(
        self,
        user_agent: str,
        *,
        transport: JsonTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC EDGAR user agent must be non-empty")
        if timeout <= 0:
            raise ValueError("SEC EDGAR HTTP timeout must be positive")
        self._user_agent = user_agent.strip()
        self._transport = transport or UrllibJsonTransport()
        self._timeout = timeout

    def get_ticker_associations(self) -> tuple[SecTickerAssociation, ...]:
        payload = self._get_json(_SEC_TICKERS_URL)
        if not isinstance(payload, dict):
            raise SecEdgarResponseError("SEC ticker response must be a JSON object")
        fields = payload.get("fields")
        rows = payload.get("data")
        if not isinstance(fields, list) or not isinstance(rows, list):
            raise SecEdgarResponseError("SEC ticker response is missing fields/data arrays")
        field_names = [str(item) for item in fields]
        required = {"cik", "name", "ticker", "exchange"}
        if not required.issubset(field_names):
            raise SecEdgarResponseError("SEC ticker response is missing required columns")

        result: list[SecTickerAssociation] = []
        for raw_row in rows:
            if not isinstance(raw_row, list) or len(raw_row) != len(field_names):
                raise SecEdgarResponseError("SEC ticker response contains a malformed row")
            row = dict(zip(field_names, raw_row, strict=True))
            result.append(
                SecTickerAssociation(
                    cik=_required_int(row.get("cik"), field="cik"),
                    name=_required_text(row.get("name"), field="name"),
                    ticker=_required_text(row.get("ticker"), field="ticker"),
                    exchange=_required_text(row.get("exchange"), field="exchange"),
                )
            )
        return tuple(result)

    def get_submissions(self, cik: int) -> Mapping[str, Any]:
        if cik <= 0:
            raise ValueError("SEC CIK must be positive")
        url = _SEC_SUBMISSIONS_URL.format(cik=f"{cik:010d}")
        payload = self._get_json(url)
        if not isinstance(payload, dict):
            raise SecEdgarResponseError("SEC submissions response must be a JSON object")
        return payload

    def _get_json(self, url: str) -> Any:
        raw = self._transport.get(
            url,
            user_agent=self._user_agent,
            timeout=self._timeout,
        )
        try:
            return json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecEdgarResponseError("SEC EDGAR returned invalid JSON") from exc


class SecEdgarAdapter:
    """Current issuer/ticker reference adapter with explicit identity limitations."""

    provider_id = "sec_edgar"

    def __init__(self, client: SecEdgarClient) -> None:
        self._client = client

    @classmethod
    def from_user_agent(
        cls,
        user_agent: str,
        *,
        timeout: float = 30.0,
    ) -> SecEdgarAdapter:
        return cls(SecEdgarClient(user_agent, timeout=timeout))

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset({DataFamily.INSTRUMENTS}),
            adjustment_modes=frozenset(),
            earliest_daily_bar_date=None,
            supports_delisted=False,
            supports_symbol_history=False,
            timestamp_convention=(
                "Current SEC issuer/ticker association snapshot; no market timestamps"
            ),
            known_limitations=(
                "CIK identifies an SEC filer/entity, not a permanent listed security.",
                "The current ticker/exchange association file is not a point-in-time universe history.",
                "SEC does not guarantee complete accuracy or scope of ticker associations.",
                "EDGAR supplies filings/reference data, not daily OHLCV.",
                (
                    "Former company names in submissions metadata are issuer history, "
                    "not security-symbol history."
                ),
            ),
        )

    def health_check(self) -> ProviderHealth:
        try:
            associations = self._client.get_ticker_associations()
        except SecEdgarApiError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
            )
        if not associations:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.DEGRADED,
                message="SEC ticker association file returned no rows",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        if as_of is not None:
            raise SecEdgarCapabilityError(
                "SEC current ticker associations cannot be treated as a historical "
                "point-in-time snapshot"
            )
        return tuple(
            self._to_provider_instrument(item)
            for item in self._client.get_ticker_associations()
        )

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        del provider_instrument_ids
        raise SecEdgarCapabilityError(
            "SEC issuer metadata is not accepted as complete security symbol history"
        )

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        del request
        raise SecEdgarCapabilityError("SEC EDGAR does not provide daily OHLCV")

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        del request
        raise SecEdgarCapabilityError(
            "SEC filings may evidence corporate actions but are not yet an accepted action feed"
        )

    def get_issuer_metadata(self, cik: int) -> Mapping[str, Any]:
        """Return issuer submissions metadata for identity reconciliation work."""

        return self._client.get_submissions(cik)

    def _to_provider_instrument(self, item: SecTickerAssociation) -> ProviderInstrument:
        provider_instrument_id = f"sec_edgar:cik:{item.cik}:ticker:{item.ticker}"
        return ProviderInstrument(
            provider_id=self.provider_id,
            provider_instrument_id=provider_instrument_id,
            symbol=item.ticker,
            name=item.name,
            exchange=item.exchange,
            security_type=SecurityType.OTHER,
            currency="USD",
            active=True,
            first_trade_date=None,
            end_date=None,
            source_fields={
                "cik": item.cik,
                "identity_warning": (
                    "CIK is issuer-level; ticker association is current and not canonical "
                    "security identity"
                ),
            },
        )


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SecEdgarResponseError(f"SEC response is missing required text field {field}")
    return value.strip()


def _required_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise SecEdgarResponseError(f"SEC response has invalid integer field {field}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise SecEdgarResponseError(f"SEC response is missing required integer field {field}")
