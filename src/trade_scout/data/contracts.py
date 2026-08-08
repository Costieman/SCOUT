"""Canonical and provider-boundary contracts for the Trade Scout data foundation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import NewType, cast

InstrumentId = NewType("InstrumentId", str)
DatasetVersion = NewType("DatasetVersion", str)


class QualityStatus(StrEnum):
    """Explicit data-quality state carried by canonical records and batches."""

    PASS = "PASS"
    WARN = "WARN"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"


class PriceRepresentation(StrEnum):
    """Price representation explicitly requested by a downstream consumer."""

    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"


class SecurityType(StrEnum):
    """Initial security classifications needed by the equity data foundation."""

    COMMON_STOCK = "common_stock"
    PREFERRED_STOCK = "preferred_stock"
    ETF = "etf"
    ETN = "etn"
    CLOSED_END_FUND = "closed_end_fund"
    WARRANT = "warrant"
    RIGHT = "right"
    OTHER = "other"


class CorporateActionType(StrEnum):
    """Corporate-action families retained by the canonical layer."""

    SPLIT = "split"
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    SYMBOL_CHANGE = "symbol_change"
    MERGER = "merger"
    SPIN_OFF = "spin_off"
    DELISTING = "delisting"


class IngestionJobState(StrEnum):
    """Durable ingestion states defined by the provider/ingestion specification."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    INGESTED = "INGESTED"
    VALIDATING = "VALIDATING"
    QUARANTINED = "QUARANTINED"
    PROMOTED = "PROMOTED"


@dataclass(frozen=True, slots=True)
class InstrumentRecord:
    """Canonical instrument-master record keyed by a permanent internal identifier."""

    instrument_id: InstrumentId
    primary_symbol: str
    name: str
    exchange: str
    security_type: SecurityType
    currency: str
    first_trade_date: date | None
    delisting_date: date | None
    provider_ids: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class SymbolHistoryRecord:
    """Dated symbol assignment for a canonical instrument."""

    instrument_id: InstrumentId
    symbol: str
    exchange: str
    effective_from: date
    effective_to: date | None


@dataclass(frozen=True, slots=True)
class CorporateActionRecord:
    """Canonical corporate action with preserved provider provenance."""

    action_id: str
    instrument_id: InstrumentId
    action_type: CorporateActionType
    effective_date: date
    provider_id: str
    source_event_id: str | None
    source_fields: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True, slots=True)
class DailyBar:
    """Canonical daily OHLCV record preserving raw and split-adjusted representations."""

    instrument_id: InstrumentId
    trade_date: date
    open_raw: float
    high_raw: float
    low_raw: float
    close_raw: float
    volume_raw: int
    split_factor: float
    dividend_cash: float
    open_split_adjusted: float | None
    high_split_adjusted: float | None
    low_split_adjusted: float | None
    close_split_adjusted: float | None
    provider_id: str
    dataset_version: DatasetVersion
    quality_status: QualityStatus


@dataclass(frozen=True, slots=True)
class ResearchBar:
    """Vendor-independent bar contract consumed by downstream research modules."""

    instrument_id: InstrumentId
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    eligibility: bool
    quality_status: QualityStatus
    dataset_version: DatasetVersion
    price_representation: PriceRepresentation


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Minimum immutable provenance required for an ingested raw batch."""

    provider_id: str
    retrieval_time: datetime
    request_parameters: Mapping[str, str | int | float | bool | None]
    checksum: str
    provider_revision: str | None = None


class PriceRepresentationUnavailableError(ValueError):
    """Raised when a requested canonical price representation is unavailable."""


def to_research_bar(
    bar: DailyBar,
    *,
    representation: PriceRepresentation,
    eligibility: bool,
) -> ResearchBar:
    """Materialize the stable ResearchBar contract without silently changing price basis."""

    if representation is PriceRepresentation.RAW:
        prices = (bar.open_raw, bar.high_raw, bar.low_raw, bar.close_raw)
    else:
        adjusted = (
            bar.open_split_adjusted,
            bar.high_split_adjusted,
            bar.low_split_adjusted,
            bar.close_split_adjusted,
        )
        if any(value is None for value in adjusted):
            raise PriceRepresentationUnavailableError(
                f"split-adjusted OHLC unavailable for {bar.instrument_id} on {bar.trade_date}"
            )
        prices = cast(tuple[float, float, float, float], adjusted)

    return ResearchBar(
        instrument_id=bar.instrument_id,
        trade_date=bar.trade_date,
        open=prices[0],
        high=prices[1],
        low=prices[2],
        close=prices[3],
        volume=bar.volume_raw,
        eligibility=eligibility,
        quality_status=bar.quality_status,
        dataset_version=bar.dataset_version,
        price_representation=representation,
    )
