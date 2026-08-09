"""EODHD-specific evidence model for deterministic correction-lookback updates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import DailyBar, DatasetVersion
from trade_scout.data.revisions import CanonicalRevisionResult, build_canonical_revision


@dataclass(frozen=True, slots=True)
class EodhdDailyUpdateEvidence:
    """Deterministic summary of one EODHD canonical daily-update candidate."""

    parent_dataset_version: DatasetVersion
    target_dataset_version: DatasetVersion
    correction_window_start: date
    incoming_count: int
    added_count: int
    revised_count: int
    unchanged_incoming_count: int
    carried_forward_count: int
    requires_new_version: bool
    revision: CanonicalRevisionResult


def assess_eodhd_daily_update(
    base_bars: Iterable[DailyBar],
    incoming_bars: Iterable[DailyBar],
    *,
    target_dataset_version: DatasetVersion,
    correction_window_start: date,
) -> EodhdDailyUpdateEvidence:
    """Apply the canonical revision policy and retain explicit EODHD update evidence.

    This function is provider-specific bookkeeping over the provider-neutral revision engine. It
    does not claim that EODHD correction behavior has been demonstrated live; it makes such a
    demonstration measurable and fail-closed once real provider observations are supplied.
    """

    base = tuple(base_bars)
    incoming = tuple(incoming_bars)
    if any(bar.provider_id != "eodhd" for bar in (*base, *incoming)):
        raise ValueError("EODHD daily update evidence requires provider_id='eodhd' for all bars")

    revision = build_canonical_revision(
        base,
        incoming,
        target_dataset_version=target_dataset_version,
        correction_window_start=correction_window_start,
    )
    return EodhdDailyUpdateEvidence(
        parent_dataset_version=revision.parent_dataset_version,
        target_dataset_version=revision.target_dataset_version,
        correction_window_start=correction_window_start,
        incoming_count=len(incoming),
        added_count=len(revision.added),
        revised_count=len(revision.revised),
        unchanged_incoming_count=len(revision.unchanged_incoming),
        carried_forward_count=revision.carried_forward_count,
        requires_new_version=revision.requires_new_version,
        revision=revision,
    )
