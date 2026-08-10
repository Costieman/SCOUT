"""Controlled promotion and verification for provenance-preserving A+B canonical datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetManifest,
    DatasetPromotionRequest,
)
from trade_scout.data.composite_promotion import (
    COMPOSITE_CANONICAL_PROVIDER_ID,
    CompositeCanonicalizationResult,
    CompositeRowProvenance,
)
from trade_scout.data.composite_provenance_store import (
    CompositeProvenanceManifest,
    CompositeProvenanceStore,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion


class CompositeDatasetIntegrityError(RuntimeError):
    """Raised when canonical bars and row provenance do not form one verified dataset."""


@dataclass(frozen=True, slots=True)
class CompositeDatasetManifest:
    canonical: CanonicalDatasetManifest
    provenance: CompositeProvenanceManifest


@dataclass(frozen=True, slots=True)
class VerifiedCompositeDataset:
    bars: tuple[DailyBar, ...]
    provenance: tuple[CompositeRowProvenance, ...]
    manifest: CompositeDatasetManifest


class CompositeDatasetStore:
    """Promote and load A+B data only when canonical rows and provenance agree."""

    def __init__(self, root: Path) -> None:
        self._canonical = CanonicalDailyBarStore(root)
        self._provenance = CompositeProvenanceStore(root)

    def promote(
        self,
        result: CompositeCanonicalizationResult,
        request: DatasetPromotionRequest,
    ) -> CompositeDatasetManifest:
        """Register provenance first, then canonical bars, and verify the joined dataset.

        Provenance-first registration is intentional. If canonical promotion fails, an orphaned
        provenance sidecar cannot be served as research data and an exact retry is idempotent. The
        inverse ordering could leave a canonical composite dataset visible without its source-row
        provenance, which this service explicitly avoids.
        """

        _validate_promotion(result, request)
        provenance_manifest = self._provenance.write(
            request.dataset_version,
            result.provenance,
        )
        canonical_manifest = self._canonical.promote(result.bars, request)
        manifest = CompositeDatasetManifest(
            canonical=canonical_manifest,
            provenance=provenance_manifest,
        )
        verified = self.load(request.dataset_version)
        if verified.manifest != manifest:
            raise CompositeDatasetIntegrityError(
                "composite dataset verification returned a different immutable manifest"
            )
        return manifest

    def load(self, dataset_version: DatasetVersion) -> VerifiedCompositeDataset:
        """Fail closed unless canonical bars and provenance are both present and consistent."""

        canonical_manifest = self._canonical.get_manifest(dataset_version)
        provenance_manifest = self._provenance.get_manifest(dataset_version)
        if canonical_manifest is None and provenance_manifest is None:
            raise CompositeDatasetIntegrityError(
                f"composite dataset {dataset_version} is not registered"
            )
        if canonical_manifest is None or provenance_manifest is None:
            raise CompositeDatasetIntegrityError(
                f"composite dataset {dataset_version} has incomplete canonical/provenance state"
            )
        if canonical_manifest.primary_provider_id != COMPOSITE_CANONICAL_PROVIDER_ID:
            raise CompositeDatasetIntegrityError(
                f"dataset {dataset_version} is not registered as a Trade Scout composite"
            )

        bars = self._canonical.load(dataset_version)
        provenance = self._provenance.load(provenance_manifest)
        _verify_join(bars, provenance, dataset_version)
        return VerifiedCompositeDataset(
            bars=bars,
            provenance=provenance,
            manifest=CompositeDatasetManifest(
                canonical=canonical_manifest,
                provenance=provenance_manifest,
            ),
        )


def _validate_promotion(
    result: CompositeCanonicalizationResult,
    request: DatasetPromotionRequest,
) -> None:
    if request.primary_provider_id != COMPOSITE_CANONICAL_PROVIDER_ID:
        raise ValueError(
            "composite promotion request must use the Trade Scout composite provider identity"
        )
    if result.normalization_issues:
        raise ValueError("composite promotion is blocked by unresolved normalization issues")
    if not result.bars:
        raise ValueError("composite promotion requires at least one accepted canonical bar")
    included = tuple(item for item in result.provenance if item.included)
    if len(included) != len(result.bars):
        raise ValueError("included provenance count must equal canonical bar count")
    for bar in result.bars:
        if bar.provider_id != COMPOSITE_CANONICAL_PROVIDER_ID:
            raise ValueError("composite canonical bars must use the composite provider identity")
        if bar.dataset_version != request.dataset_version:
            raise ValueError("composite bar dataset version does not match promotion request")
    _verify_join(result.bars, result.provenance, request.dataset_version)


def _verify_join(
    bars: tuple[DailyBar, ...],
    provenance: tuple[CompositeRowProvenance, ...],
    dataset_version: DatasetVersion,
) -> None:
    bar_keys = {(str(bar.instrument_id), bar.trade_date.isoformat()) for bar in bars}
    included = tuple(item for item in provenance if item.included)
    provenance_keys = {(item.instrument_id, item.trade_date) for item in included}
    if bar_keys != provenance_keys:
        raise CompositeDatasetIntegrityError(
            f"canonical/provenance row keys differ for composite dataset {dataset_version}"
        )
    if len(bar_keys) != len(bars) or len(provenance_keys) != len(included):
        raise CompositeDatasetIntegrityError(
            f"duplicate canonical/provenance keys exist for composite dataset {dataset_version}"
        )
    for item in included:
        if item.canonical_provider_id != COMPOSITE_CANONICAL_PROVIDER_ID:
            raise CompositeDatasetIntegrityError(
                f"row provenance has the wrong canonical provider for {item.instrument_id}"
            )
        if item.selected_source_provider_id is None:
            raise CompositeDatasetIntegrityError(
                f"included row provenance lacks a source provider for {item.instrument_id}"
            )
        if item.selected_source_provider_instrument_id is None:
            raise CompositeDatasetIntegrityError(
                f"included row provenance lacks a provider instrument ID for {item.instrument_id}"
            )
