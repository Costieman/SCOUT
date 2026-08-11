"""Fail-closed promotion of reviewed identity candidates into the immutable instrument master."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.data.instrument_storage import (
    InstrumentMasterManifest,
    InstrumentMasterNotFoundError,
    InstrumentMasterPromotionRequest,
    InstrumentMasterStore,
)
from trade_scout.data.reviewed_identity_seed_source import load_reviewed_identity_seed_source
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotCandidate,
    build_reviewed_identity_snapshot_candidate,
    load_reviewed_identity_snapshot_candidate,
)


class ReviewedIdentityPromotionError(RuntimeError):
    """Raised when reviewed identity evidence is not safe to promote."""


@dataclass(frozen=True, slots=True)
class ReviewedIdentityPromotionResult:
    """Verified immutable instrument-master promotion result."""

    manifest: InstrumentMasterManifest
    candidate: ReviewedIdentitySnapshotCandidate
    already_registered: bool


def promote_reviewed_identity_candidate(
    *,
    candidate_path: Path,
    seed_path: Path,
    lineage_audit_path: Path,
    store_root: Path,
    promoted_at: datetime | None = None,
) -> ReviewedIdentityPromotionResult:
    """Rebuild, compare, promote, and reload one reviewed identity candidate.

    The gate intentionally does not accept provider price rows. A persisted candidate is first
    reloaded and structurally validated, then rebuilt from the checked-in reviewed seed source and
    exact lineage-audit source. Promotion is allowed only when the persisted and rebuilt candidates
    are equal and no reviewed-history coverage gaps remain.
    """

    persisted = load_reviewed_identity_snapshot_candidate(candidate_path)
    seed_set = load_reviewed_identity_seed_source(seed_path)
    rebuilt = build_reviewed_identity_snapshot_candidate(
        seed_set=seed_set,
        lineage_audit_path=lineage_audit_path,
    )

    if persisted != rebuilt:
        raise ReviewedIdentityPromotionError(
            "persisted identity candidate does not exactly match a rebuild from current "
            "seed/audit evidence"
        )
    if not rebuilt.promotion_ready:
        raise ReviewedIdentityPromotionError(
            "reviewed identity candidate has unresolved coverage gaps and cannot be promoted"
        )

    source_batch_ids = (
        f"reviewed-identity-seed-sha256:{rebuilt.identity_seed_sha256}",
        f"tiingo-lineage-audit-sha256:{rebuilt.lineage_audit_sha256}",
    )
    store = InstrumentMasterStore(store_root)

    try:
        existing = store.get_manifest(rebuilt.snapshot_version)
    except InstrumentMasterNotFoundError:
        existing = None

    if existing is not None:
        _verify_existing_manifest(existing, rebuilt, source_batch_ids)
        loaded = store.load(rebuilt.snapshot_version)
        if (
            loaded.instruments != rebuilt.instruments
            or loaded.symbol_history != rebuilt.symbol_history
        ):
            raise ReviewedIdentityPromotionError(
                "registered instrument master does not exactly match the reviewed identity "
                "candidate"
            )
        return ReviewedIdentityPromotionResult(
            manifest=existing,
            candidate=rebuilt,
            already_registered=True,
        )

    created_at = promoted_at or datetime.now(UTC)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ReviewedIdentityPromotionError("promoted_at must be timezone-aware")

    manifest = store.promote(
        rebuilt.instruments,
        rebuilt.symbol_history,
        InstrumentMasterPromotionRequest(
            snapshot_version=rebuilt.snapshot_version,
            primary_provider_id=rebuilt.primary_provider_id,
            created_at=created_at,
            source_batch_ids=source_batch_ids,
            identity_definition_version=rebuilt.identity_definition_version,
            symbol_history_definition_version=rebuilt.symbol_history_definition_version,
        ),
    )
    loaded = store.load(rebuilt.snapshot_version)
    if loaded.instruments != rebuilt.instruments or loaded.symbol_history != rebuilt.symbol_history:
        raise ReviewedIdentityPromotionError(
            "post-promotion instrument-master reload does not match the reviewed candidate"
        )

    return ReviewedIdentityPromotionResult(
        manifest=manifest,
        candidate=rebuilt,
        already_registered=False,
    )


def _verify_existing_manifest(
    manifest: InstrumentMasterManifest,
    candidate: ReviewedIdentitySnapshotCandidate,
    source_batch_ids: tuple[str, ...],
) -> None:
    expected = {
        "snapshot_version": candidate.snapshot_version,
        "primary_provider_id": candidate.primary_provider_id,
        "source_batch_ids": source_batch_ids,
        "identity_definition_version": candidate.identity_definition_version,
        "symbol_history_definition_version": candidate.symbol_history_definition_version,
        "instrument_count": len(candidate.instruments),
        "symbol_history_count": len(candidate.symbol_history),
    }
    actual = {
        "snapshot_version": manifest.snapshot_version,
        "primary_provider_id": manifest.primary_provider_id,
        "source_batch_ids": manifest.source_batch_ids,
        "identity_definition_version": manifest.identity_definition_version,
        "symbol_history_definition_version": manifest.symbol_history_definition_version,
        "instrument_count": manifest.instrument_count,
        "symbol_history_count": manifest.symbol_history_count,
    }
    if actual != expected:
        raise ReviewedIdentityPromotionError(
            "existing instrument-master registration conflicts with reviewed candidate provenance"
        )


__all__ = [
    "ReviewedIdentityPromotionError",
    "ReviewedIdentityPromotionResult",
    "promote_reviewed_identity_candidate",
]
