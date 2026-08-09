"""Promote provider evaluation bars only after explicit normalization and provenance gates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetManifest,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import DatasetVersion, InstrumentRecord, QualityStatus
from trade_scout.data.normalization import (
    DailyBarNormalizationResult,
    normalize_provider_daily_bars,
)
from trade_scout.data.provider import ProviderDailyBar


class ProviderPromotionError(ValueError):
    """Raised when provider evidence is not safe to promote into a canonical dataset version."""


@dataclass(frozen=True, slots=True)
class ProviderPromotionResult:
    """Canonical promotion plus the exact normalization evidence used by the gate."""

    normalization: DailyBarNormalizationResult
    manifest: CanonicalDatasetManifest


def promote_provider_daily_bar_evaluation(
    provider_bars: Iterable[ProviderDailyBar],
    *,
    instruments: Iterable[InstrumentRecord],
    store: CanonicalDailyBarStore,
    dataset_id: str,
    dataset_version: DatasetVersion,
    primary_provider_id: str,
    source_batch_ids: tuple[str, ...],
    created_at: datetime,
    transformation_version: str,
    adjustment_policy_version: str,
    universe_construction_version: str,
    quality_check_version: str,
) -> ProviderPromotionResult:
    """Normalize and promote one bounded provider evaluation without weakening provenance.

    The caller must supply immutable raw source-batch identities. Unresolved provider identities,
    incomplete adjustment metadata, and records that reach QUARANTINE/REJECT prevent promotion.
    WARN quality observations remain eligible because the canonical quality contract preserves
    their status explicitly.
    """

    bars = tuple(provider_bars)
    if not bars:
        raise ProviderPromotionError("provider promotion requires at least one daily bar")
    if not source_batch_ids:
        raise ProviderPromotionError("provider promotion requires immutable raw source batch IDs")
    if len(source_batch_ids) != len(set(source_batch_ids)):
        raise ProviderPromotionError("provider promotion source batch IDs must be unique")
    if any(not batch_id.strip() for batch_id in source_batch_ids):
        raise ProviderPromotionError("provider promotion source batch IDs must be non-empty")

    provider_ids = {bar.provider_id for bar in bars}
    if provider_ids != {primary_provider_id}:
        raise ProviderPromotionError(
            "provider promotion bars must all come from the declared primary provider"
        )

    normalization = normalize_provider_daily_bars(
        bars,
        instruments=instruments,
        dataset_version=dataset_version,
    )
    if normalization.normalization_issues:
        raise ProviderPromotionError(
            "provider promotion blocked by unresolved normalization issues"
        )
    blocked_quality = tuple(
        issue
        for issue in normalization.quality_issues
        if issue.status in {QualityStatus.QUARANTINE, QualityStatus.REJECT}
    )
    if blocked_quality:
        raise ProviderPromotionError(
            "provider promotion blocked by quarantined or rejected quality evidence"
        )

    request = DatasetPromotionRequest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        primary_provider_id=primary_provider_id,
        created_at=created_at,
        source_batch_ids=source_batch_ids,
        transformation_version=transformation_version,
        adjustment_policy_version=adjustment_policy_version,
        universe_construction_version=universe_construction_version,
        quality_check_version=quality_check_version,
    )
    manifest = store.promote(normalization.bars, request)
    return ProviderPromotionResult(normalization=normalization, manifest=manifest)
