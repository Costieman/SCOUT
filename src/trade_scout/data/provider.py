"""Provider-neutral request/response contracts and adapter protocol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol, runtime_checkable

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation, SecurityType


class DataFamily(StrEnum):
    """Data families a provider adapter may declare as supported."""

    INSTRUMENTS = "instruments"
    SYMBOL_HISTORY = "symbol_history"
    DAILY_BARS = "daily_bars"
    CORPORATE_ACTIONS = "corporate_actions"
    STATUS_DELISTINGS = "status_delistings"
    MARKET_CALENDAR = "market_calendar"


class ProviderHealthStatus(StrEnum):
    """Provider health result independent of any vendor SDK."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Machine-readable capability declaration for one provider adapter."""

    provider_id: str
    data_families: frozenset[DataFamily]
    adjustment_modes: frozenset[PriceRepresentation]
    earliest_daily_bar_date: date | None
    supports_delisted: bool
    supports_symbol_history: bool
    timestamp_convention: str
    known_limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Health check result returned by an adapter."""

    provider_id: str
    status: ProviderHealthStatus
    message: str | None = None


@dataclass(frozen=True, slots=True)
class DailyBarRequest:
    """Provider-neutral request for a bounded daily-bar retrieval."""

    start: date
    end: date
    provider_symbols: tuple[str, ...] | None = None
    adjustment: PriceRepresentation = PriceRepresentation.RAW
    run_id: str | None = None

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("daily-bar request end date must be on or after start date")


@dataclass(frozen=True, slots=True)
class CorporateActionRequest:
    """Provider-neutral request for corporate actions."""

    start: date
    end: date
    provider_symbols: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("corporate-action request end date must be on or after start date")


@dataclass(frozen=True, slots=True)
class ProviderInstrument:
    """Normalized provider reference record before canonical identifier resolution."""

    provider_id: str
    provider_instrument_id: str
    symbol: str
    name: str
    exchange: str
    security_type: SecurityType
    currency: str
    active: bool
    first_trade_date: date | None
    end_date: date | None
    source_fields: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True, slots=True)
class ProviderSymbolHistory:
    """Provider symbol-history record before canonical identifier resolution."""

    provider_id: str
    provider_instrument_id: str
    symbol: str
    exchange: str
    effective_from: date
    effective_to: date | None


@dataclass(frozen=True, slots=True)
class ProviderDailyBar:
    """Normalized provider daily bar retaining provider identity and raw values."""

    provider_id: str
    provider_instrument_id: str
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    split_factor: float | None = None
    dividend_cash: float | None = None
    adjusted_open: float | None = None
    adjusted_high: float | None = None
    adjusted_low: float | None = None
    adjusted_close: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderCorporateAction:
    """Normalized provider corporate action retaining the original event identity."""

    provider_id: str
    provider_instrument_id: str
    source_event_id: str | None
    action_type: CorporateActionType
    effective_date: date
    source_fields: Mapping[str, str | int | float | bool | None]


@runtime_checkable
class ProviderAdapter(Protocol):
    """Common vendor boundary required by the Trade Scout ingestion service."""

    provider_id: str

    def describe_capabilities(self) -> ProviderCapabilities: ...

    def health_check(self) -> ProviderHealth: ...

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]: ...

    def get_symbol_history(
        self, *, provider_instrument_ids: Sequence[str] | None = None
    ) -> Sequence[ProviderSymbolHistory]: ...

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]: ...

    def get_corporate_actions(
        self, request: CorporateActionRequest
    ) -> Sequence[ProviderCorporateAction]: ...
