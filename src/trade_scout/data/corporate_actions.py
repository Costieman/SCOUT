"""Canonical corporate-action identity resolution and normalization."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid5

from trade_scout.data.contracts import (
    CorporateActionRecord,
    CorporateActionType,
    InstrumentId,
    InstrumentRecord,
)
from trade_scout.data.instrument_master import resolve_provider_identity
from trade_scout.data.provider import ProviderCorporateAction

_ACTION_NAMESPACE = UUID("315de11c-fd8b-5f55-9183-42a117c62d67")


class CorporateActionConflictError(ValueError):
    """Raised when provider corporate-action records cannot be normalized unambiguously."""


@dataclass(frozen=True, slots=True)
class UnresolvedCorporateAction:
    """Provider action deliberately not linked because permanent identity is unavailable."""

    provider_id: str
    provider_instrument_id: str
    source_event_id: str | None
    action_type: CorporateActionType
    effective_date: date


@dataclass(frozen=True, slots=True)
class CorporateActionNormalizationResult:
    """Resolved canonical actions plus records retained as explicit unresolved evidence."""

    records: tuple[CorporateActionRecord, ...]
    unresolved: tuple[UnresolvedCorporateAction, ...]


def normalize_provider_corporate_actions(
    records: Iterable[ProviderCorporateAction],
    instruments: Iterable[InstrumentRecord],
) -> CorporateActionNormalizationResult:
    """Resolve provider actions only through exact permanent provider identities."""

    instrument_records = tuple(instruments)
    canonical_by_id: dict[str, CorporateActionRecord] = {}
    unresolved: list[UnresolvedCorporateAction] = []

    for record in records:
        _validate_provider_action(record)
        instrument_id = resolve_provider_identity(
            instrument_records,
            provider_id=record.provider_id,
            provider_instrument_id=record.provider_instrument_id,
        )
        if instrument_id is None:
            unresolved.append(
                UnresolvedCorporateAction(
                    provider_id=record.provider_id,
                    provider_instrument_id=record.provider_instrument_id,
                    source_event_id=record.source_event_id,
                    action_type=record.action_type,
                    effective_date=record.effective_date,
                )
            )
            continue

        action_id = derive_corporate_action_id(record)
        normalized = CorporateActionRecord(
            action_id=action_id,
            instrument_id=instrument_id,
            action_type=record.action_type,
            effective_date=record.effective_date,
            provider_id=record.provider_id,
            source_event_id=record.source_event_id,
            source_fields=dict(record.source_fields),
        )
        existing = canonical_by_id.get(action_id)
        if existing is not None and existing != normalized:
            raise CorporateActionConflictError(
                f"corporate action {action_id} has conflicting provider records"
            )
        canonical_by_id[action_id] = normalized

    canonical = tuple(
        sorted(
            canonical_by_id.values(),
            key=lambda item: (
                item.effective_date,
                str(item.instrument_id),
                str(item.action_type),
                item.action_id,
            ),
        )
    )
    _validate_no_ambiguous_source_less_events(canonical)
    return CorporateActionNormalizationResult(
        records=canonical,
        unresolved=tuple(
            sorted(
                unresolved,
                key=lambda item: (
                    item.effective_date,
                    item.provider_id,
                    item.provider_instrument_id,
                    str(item.action_type),
                ),
            )
        ),
    )


def derive_corporate_action_id(record: ProviderCorporateAction) -> str:
    """Derive a stable internal action ID without using ticker or mutable company metadata."""

    provider_id = record.provider_id.strip().lower()
    provider_instrument_id = record.provider_instrument_id.strip()
    if not provider_id or not provider_instrument_id:
        raise CorporateActionConflictError("provider action identity must be non-empty")

    if record.source_event_id is not None:
        source_event_id = record.source_event_id.strip()
        if not source_event_id:
            raise CorporateActionConflictError("source_event_id must be non-empty when supplied")
        seed = f"{provider_id}:{provider_instrument_id}:event:{source_event_id}"
    else:
        seed = (
            f"{provider_id}:{provider_instrument_id}:"
            f"{record.action_type}:{record.effective_date.isoformat()}"
        )
    return f"tca_{uuid5(_ACTION_NAMESPACE, seed).hex}"


def _validate_provider_action(record: ProviderCorporateAction) -> None:
    if not record.provider_id.strip() or not record.provider_instrument_id.strip():
        raise CorporateActionConflictError("provider action identity must be non-empty")
    if record.source_event_id is not None and not record.source_event_id.strip():
        raise CorporateActionConflictError("source_event_id must be non-empty when supplied")
    for key, value in record.source_fields.items():
        if not key.strip():
            raise CorporateActionConflictError("corporate-action source field keys must be non-empty")
        if value is not None and not isinstance(value, str | int | float | bool):
            raise CorporateActionConflictError(
                f"corporate-action source field {key} has unsupported value type"
            )


def _validate_no_ambiguous_source_less_events(records: tuple[CorporateActionRecord, ...]) -> None:
    seen: dict[tuple[InstrumentId, CorporateActionType, date, str], CorporateActionRecord] = {}
    for record in records:
        if record.source_event_id is not None:
            continue
        key = (
            record.instrument_id,
            record.action_type,
            record.effective_date,
            record.provider_id,
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = record
            continue
        if _source_fields_json(existing.source_fields) != _source_fields_json(record.source_fields):
            raise CorporateActionConflictError(
                "multiple source-event-less actions share instrument/type/date/provider identity"
            )


def _source_fields_json(fields: Mapping[str, str | int | float | bool | None]) -> str:
    return json.dumps(dict(fields), sort_keys=True, separators=(",", ":"))
