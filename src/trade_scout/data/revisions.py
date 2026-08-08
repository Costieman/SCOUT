"""Deterministic canonical dataset revision planning for incremental daily updates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId


class RevisionConflictError(ValueError):
    """Raised when an incremental revision request is ambiguous or violates the correction window."""


@dataclass(frozen=True, slots=True)
class RevisedObservation:
    """One canonical instrument/session observation changed by an incremental update."""

    instrument_id: InstrumentId
    trade_date: date


@dataclass(frozen=True, slots=True)
class CanonicalRevisionResult:
    """Full immutable revision candidate plus a deterministic change summary."""

    parent_dataset_version: DatasetVersion
    target_dataset_version: DatasetVersion
    bars: tuple[DailyBar, ...]
    added: tuple[RevisedObservation, ...]
    revised: tuple[RevisedObservation, ...]
    unchanged_incoming: tuple[RevisedObservation, ...]
    carried_forward_count: int

    @property
    def requires_new_version(self) -> bool:
        """Return whether incoming data changed the canonical content."""

        return bool(self.added or self.revised)


def build_canonical_revision(
    base_bars: Iterable[DailyBar],
    incoming_bars: Iterable[DailyBar],
    *,
    target_dataset_version: DatasetVersion,
    correction_window_start: date,
) -> CanonicalRevisionResult:
    """Append new observations and replace only explicit incoming keys inside the correction window."""

    base = tuple(base_bars)
    incoming = tuple(incoming_bars)
    if not base:
        raise RevisionConflictError("incremental revision requires an existing canonical dataset")

    parent_version = _single_dataset_version(base, label="base")
    if target_dataset_version == parent_version:
        raise RevisionConflictError("target dataset version must differ from parent dataset version")

    canonical_provider = _single_provider(base, label="base")
    _validate_unique_keys(base, label="base")
    _validate_unique_keys(incoming, label="incoming")

    if incoming:
        incoming_version = _single_dataset_version(incoming, label="incoming")
        if incoming_version != target_dataset_version:
            raise RevisionConflictError(
                f"incoming bars use {incoming_version}; expected target version {target_dataset_version}"
            )
        incoming_provider = _single_provider(incoming, label="incoming")
        if incoming_provider != canonical_provider:
            raise RevisionConflictError(
                f"incoming provider {incoming_provider} differs from canonical provider "
                f"{canonical_provider}"
            )

    for bar in incoming:
        if bar.trade_date < correction_window_start:
            raise RevisionConflictError(
                f"incoming correction for {bar.instrument_id} on {bar.trade_date} precedes "
                f"correction window {correction_window_start}"
            )

    base_by_key = {_key(bar): bar for bar in base}
    incoming_by_key = {_key(bar): bar for bar in incoming}

    added: list[RevisedObservation] = []
    revised: list[RevisedObservation] = []
    unchanged: list[RevisedObservation] = []

    for key, incoming_bar in incoming_by_key.items():
        prior = base_by_key.get(key)
        observation = RevisedObservation(
            instrument_id=incoming_bar.instrument_id,
            trade_date=incoming_bar.trade_date,
        )
        if prior is None:
            added.append(observation)
        elif _same_market_content(prior, incoming_bar):
            unchanged.append(observation)
        else:
            revised.append(observation)

    result_by_key = {
        key: replace(bar, dataset_version=target_dataset_version) for key, bar in base_by_key.items()
    }
    result_by_key.update(incoming_by_key)

    changed_existing_keys = {(_item.instrument_id, _item.trade_date) for _item in revised}
    carried_forward_count = len(base_by_key) - len(changed_existing_keys)

    return CanonicalRevisionResult(
        parent_dataset_version=parent_version,
        target_dataset_version=target_dataset_version,
        bars=tuple(sorted(result_by_key.values(), key=_sort_key)),
        added=tuple(sorted(added, key=_observation_sort_key)),
        revised=tuple(sorted(revised, key=_observation_sort_key)),
        unchanged_incoming=tuple(sorted(unchanged, key=_observation_sort_key)),
        carried_forward_count=carried_forward_count,
    )


def _single_dataset_version(bars: tuple[DailyBar, ...], *, label: str) -> DatasetVersion:
    versions = {bar.dataset_version for bar in bars}
    if len(versions) != 1:
        raise RevisionConflictError(f"{label} bars must contain exactly one dataset version")
    return next(iter(versions))


def _single_provider(bars: tuple[DailyBar, ...], *, label: str) -> str:
    providers = {bar.provider_id for bar in bars}
    if len(providers) != 1:
        raise RevisionConflictError(f"{label} bars must contain exactly one canonical provider")
    return next(iter(providers))


def _validate_unique_keys(bars: tuple[DailyBar, ...], *, label: str) -> None:
    seen: set[tuple[InstrumentId, date]] = set()
    for bar in bars:
        key = _key(bar)
        if key in seen:
            raise RevisionConflictError(
                f"{label} bars contain duplicate instrument/session key "
                f"{bar.instrument_id}:{bar.trade_date}"
            )
        seen.add(key)


def _key(bar: DailyBar) -> tuple[InstrumentId, date]:
    return bar.instrument_id, bar.trade_date


def _same_market_content(first: DailyBar, second: DailyBar) -> bool:
    return (
        first.instrument_id == second.instrument_id
        and first.trade_date == second.trade_date
        and first.open_raw == second.open_raw
        and first.high_raw == second.high_raw
        and first.low_raw == second.low_raw
        and first.close_raw == second.close_raw
        and first.volume_raw == second.volume_raw
        and first.split_factor == second.split_factor
        and first.dividend_cash == second.dividend_cash
        and first.open_split_adjusted == second.open_split_adjusted
        and first.high_split_adjusted == second.high_split_adjusted
        and first.low_split_adjusted == second.low_split_adjusted
        and first.close_split_adjusted == second.close_split_adjusted
        and first.provider_id == second.provider_id
        and first.quality_status == second.quality_status
    )


def _sort_key(bar: DailyBar) -> tuple[str, date, str]:
    return str(bar.instrument_id), bar.trade_date, bar.provider_id


def _observation_sort_key(observation: RevisedObservation) -> tuple[date, str]:
    return observation.trade_date, str(observation.instrument_id)
