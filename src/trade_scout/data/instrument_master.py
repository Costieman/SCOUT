"""Permanent instrument identity and dated symbol-history handling."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from itertools import pairwise
from types import MappingProxyType
from uuid import UUID, uuid5

from trade_scout.data.contracts import InstrumentId, InstrumentRecord, SymbolHistoryRecord
from trade_scout.data.provider import ProviderInstrument, ProviderSymbolHistory

_INSTRUMENT_NAMESPACE = UUID("f4ae1584-b917-5b6b-aab5-5432f8a3e08c")


class InstrumentIdentityConflictError(ValueError):
    """Raised when one external identity maps ambiguously to canonical instruments."""


class SymbolHistoryConflictError(ValueError):
    """Raised when dated symbol records are internally contradictory."""


@dataclass(frozen=True, slots=True)
class UnresolvedSymbolHistory:
    """Provider symbol record that could not be linked without guessing identity."""

    provider_id: str
    provider_instrument_id: str
    symbol: str
    effective_from: date
    effective_to: date | None


@dataclass(frozen=True, slots=True)
class SymbolHistoryNormalizationResult:
    """Canonical symbol records plus records deliberately left unresolved."""

    records: tuple[SymbolHistoryRecord, ...]
    unresolved: tuple[UnresolvedSymbolHistory, ...]


def derive_instrument_id(provider_id: str, provider_instrument_id: str) -> InstrumentId:
    """Derive a stable opaque ID from the first admitted non-ticker provider identity.

    The seed deliberately excludes ticker, company name, and exchange because those can change or
    be reused. The resulting identifier is an internal key, not a claim that the provider ID itself
    is a universal security identifier. Later providers must be explicitly linked to the existing
    internal ID.
    """

    normalized_provider = provider_id.strip().lower()
    normalized_external_id = provider_instrument_id.strip()
    if not normalized_provider or not normalized_external_id:
        raise ValueError("provider_id and provider_instrument_id must be non-empty")

    value = uuid5(
        _INSTRUMENT_NAMESPACE,
        f"{normalized_provider}:{normalized_external_id}",
    )
    return InstrumentId(f"tsi_{value.hex}")


def instrument_from_primary_provider(record: ProviderInstrument) -> InstrumentRecord:
    """Create a canonical instrument from a primary-provider reference record."""

    return InstrumentRecord(
        instrument_id=derive_instrument_id(record.provider_id, record.provider_instrument_id),
        primary_symbol=record.symbol,
        name=record.name,
        exchange=record.exchange,
        security_type=record.security_type,
        currency=record.currency,
        first_trade_date=record.first_trade_date,
        delisting_date=record.end_date,
        provider_ids=MappingProxyType({record.provider_id: record.provider_instrument_id}),
    )


def resolve_provider_identity(
    instruments: Iterable[InstrumentRecord],
    *,
    provider_id: str,
    provider_instrument_id: str,
) -> InstrumentId | None:
    """Resolve an exact provider identity; never fall back to ticker matching."""

    matches = tuple(
        instrument.instrument_id
        for instrument in instruments
        if instrument.provider_ids.get(provider_id) == provider_instrument_id
    )
    if len(matches) > 1:
        raise InstrumentIdentityConflictError(
            f"{provider_id}:{provider_instrument_id} maps to multiple instruments"
        )
    return matches[0] if matches else None


def link_provider_identity(
    instrument: InstrumentRecord,
    *,
    provider_id: str,
    provider_instrument_id: str,
) -> InstrumentRecord:
    """Explicitly link another provider identity to an existing canonical instrument."""

    normalized_provider = provider_id.strip()
    normalized_external_id = provider_instrument_id.strip()
    if not normalized_provider or not normalized_external_id:
        raise ValueError("provider_id and provider_instrument_id must be non-empty")

    current = instrument.provider_ids.get(normalized_provider)
    if current is not None and current != normalized_external_id:
        raise InstrumentIdentityConflictError(
            f"instrument {instrument.instrument_id} already maps {normalized_provider} to {current}"
        )

    provider_ids = dict(instrument.provider_ids)
    provider_ids[normalized_provider] = normalized_external_id
    return replace(instrument, provider_ids=MappingProxyType(provider_ids))


def normalize_symbol_history(
    records: Iterable[ProviderSymbolHistory],
    instruments: Iterable[InstrumentRecord],
) -> SymbolHistoryNormalizationResult:
    """Convert provider symbol history only through exact provider-identity links."""

    instrument_records = tuple(instruments)
    canonical: list[SymbolHistoryRecord] = []
    unresolved: list[UnresolvedSymbolHistory] = []

    for record in records:
        _validate_interval(record.effective_from, record.effective_to)
        instrument_id = resolve_provider_identity(
            instrument_records,
            provider_id=record.provider_id,
            provider_instrument_id=record.provider_instrument_id,
        )
        if instrument_id is None:
            unresolved.append(
                UnresolvedSymbolHistory(
                    provider_id=record.provider_id,
                    provider_instrument_id=record.provider_instrument_id,
                    symbol=record.symbol,
                    effective_from=record.effective_from,
                    effective_to=record.effective_to,
                )
            )
            continue

        canonical.append(
            SymbolHistoryRecord(
                instrument_id=instrument_id,
                symbol=record.symbol,
                exchange=record.exchange,
                effective_from=record.effective_from,
                effective_to=record.effective_to,
            )
        )

    deduplicated = tuple(
        sorted(
            set(canonical),
            key=lambda item: (
                str(item.instrument_id),
                item.effective_from,
                item.effective_to or date.max,
                item.symbol,
            ),
        )
    )
    _validate_non_overlapping_history(deduplicated)

    return SymbolHistoryNormalizationResult(
        records=deduplicated,
        unresolved=tuple(unresolved),
    )


def symbol_as_of(
    records: Iterable[SymbolHistoryRecord],
    *,
    instrument_id: InstrumentId,
    as_of: date,
) -> SymbolHistoryRecord | None:
    """Return the unique dated symbol assignment effective on a historical date."""

    matches = tuple(
        record
        for record in records
        if record.instrument_id == instrument_id
        and record.effective_from <= as_of
        and (record.effective_to is None or as_of <= record.effective_to)
    )
    if len(matches) > 1:
        raise SymbolHistoryConflictError(
            f"multiple symbol assignments for {instrument_id} on {as_of.isoformat()}"
        )
    return matches[0] if matches else None


def _validate_interval(effective_from: date, effective_to: date | None) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise SymbolHistoryConflictError("symbol effective_to precedes effective_from")


def _validate_non_overlapping_history(records: tuple[SymbolHistoryRecord, ...]) -> None:
    by_instrument: dict[InstrumentId, list[SymbolHistoryRecord]] = {}
    for record in records:
        by_instrument.setdefault(record.instrument_id, []).append(record)

    for instrument_id, instrument_records in by_instrument.items():
        ordered = sorted(instrument_records, key=lambda item: item.effective_from)
        for previous, current in pairwise(ordered):
            previous_end = previous.effective_to
            if previous_end is None or current.effective_from <= previous_end:
                raise SymbolHistoryConflictError(
                    f"overlapping symbol history for {instrument_id}: "
                    f"{previous.symbol} and {current.symbol}"
                )
