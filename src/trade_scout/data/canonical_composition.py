"""Compose immutable canonical daily-bar datasets without rewriting their source versions.

The composition boundary is intentionally narrow. It is designed for cases such as attaching a
separately reviewed market benchmark to an already promoted research cohort. Source datasets remain
immutable and independently auditable; the composed dataset receives a new immutable version and
retains the original raw-batch provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetManifest,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import DatasetVersion

CANONICAL_COMPOSITION_TRANSFORMATION_VERSION = "canonical-composition-v0.1"
CANONICAL_COMPOSITION_QUALITY_VERSION = "canonical-composition-quality-v0.1"


class CanonicalCompositionError(RuntimeError):
    """Raised when immutable canonical sources cannot be safely composed."""


@dataclass(frozen=True, slots=True)
class CanonicalCompositionResult:
    """Persisted target manifest plus the exact immutable source versions used."""

    manifest: CanonicalDatasetManifest
    source_dataset_versions: tuple[DatasetVersion, ...]


def compose_canonical_datasets(
    store: CanonicalDailyBarStore,
    *,
    source_dataset_versions: tuple[DatasetVersion, ...],
    target_dataset_id: str,
    target_dataset_version: DatasetVersion,
    created_at: datetime,
    universe_construction_version: str,
) -> CanonicalCompositionResult:
    """Compose disjoint all-PASS canonical sources into one new immutable dataset version.

    All sources must use the same canonical provider and adjustment policy.
    Instrument/date keys must be disjoint across source datasets. This prevents a benchmark
    attachment operation from silently replacing or voting between price observations already
    present in the research cohort.
    """

    sources = _validate_source_versions(source_dataset_versions, target_dataset_version)
    manifests = tuple(_require_source_manifest(store, version) for version in sources)
    _require_compatible_sources(manifests)

    target_bars = []
    observed_keys: set[tuple[str, object]] = set()
    for version in sources:
        for bar in store.load(version):
            key = (str(bar.instrument_id), bar.trade_date)
            if key in observed_keys:
                raise CanonicalCompositionError(
                    "canonical composition found an overlapping instrument/date key: "
                    f"instrument_id={bar.instrument_id}, trade_date={bar.trade_date}"
                )
            observed_keys.add(key)
            target_bars.append(replace(bar, dataset_version=target_dataset_version))

    source_batch_ids = tuple(
        dict.fromkeys(batch_id for manifest in manifests for batch_id in manifest.source_batch_ids)
    )
    first = manifests[0]
    manifest = store.promote(
        target_bars,
        DatasetPromotionRequest(
            dataset_id=_required_text(target_dataset_id, "target_dataset_id"),
            dataset_version=target_dataset_version,
            primary_provider_id=first.primary_provider_id,
            created_at=created_at,
            source_batch_ids=source_batch_ids,
            transformation_version=CANONICAL_COMPOSITION_TRANSFORMATION_VERSION,
            adjustment_policy_version=first.adjustment_policy_version,
            universe_construction_version=_required_text(
                universe_construction_version, "universe_construction_version"
            ),
            quality_check_version=CANONICAL_COMPOSITION_QUALITY_VERSION,
        ),
    )
    return CanonicalCompositionResult(
        manifest=manifest,
        source_dataset_versions=sources,
    )


def _validate_source_versions(
    values: tuple[DatasetVersion, ...],
    target: DatasetVersion,
) -> tuple[DatasetVersion, ...]:
    if len(values) < 2:
        raise CanonicalCompositionError(
            "canonical composition requires at least two source datasets"
        )
    if len(set(values)) != len(values):
        raise CanonicalCompositionError("canonical source dataset versions must be unique")
    if target in values:
        raise CanonicalCompositionError(
            "target dataset version must differ from every source version"
        )
    return values


def _require_source_manifest(
    store: CanonicalDailyBarStore,
    version: DatasetVersion,
) -> CanonicalDatasetManifest:
    manifest = store.get_manifest(version)
    if manifest is None:
        raise CanonicalCompositionError(f"canonical source dataset is not registered: {version}")
    quality = manifest.quality_summary
    if quality.warn_count or quality.quarantine_count or quality.reject_count:
        raise CanonicalCompositionError(
            f"canonical source dataset {version} is not all-PASS: "
            f"warn={quality.warn_count}, quarantine={quality.quarantine_count}, "
            f"reject={quality.reject_count}"
        )
    if quality.pass_count != manifest.record_count:
        raise CanonicalCompositionError(
            f"canonical source dataset {version} PASS count does not equal record count"
        )
    return manifest


def _require_compatible_sources(manifests: tuple[CanonicalDatasetManifest, ...]) -> None:
    providers = {manifest.primary_provider_id for manifest in manifests}
    if len(providers) != 1:
        raise CanonicalCompositionError(
            "canonical composition currently requires one common primary provider"
        )
    adjustment_policies = {manifest.adjustment_policy_version for manifest in manifests}
    if len(adjustment_policies) != 1:
        raise CanonicalCompositionError(
            "canonical composition requires identical adjustment-policy versions"
        )


def _required_text(value: str, field: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} must be non-empty")
    return stripped
