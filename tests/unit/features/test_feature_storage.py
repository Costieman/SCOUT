from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.data.contracts import DatasetVersion
from trade_scout.features.initial import (
    INITIAL_FEATURE_SET,
    compute_initial_feature_frame,
    initial_feature_definition_sha256,
)
from trade_scout.features.storage import (
    FeatureSnapshotConflictError,
    FeatureSnapshotPromotionRequest,
    FeatureSnapshotStore,
)
from tests.unit.features.test_initial_features import _bars


def _request(*, source_checksum: str = "a" * 64) -> FeatureSnapshotPromotionRequest:
    return FeatureSnapshotPromotionRequest(
        dataset_version=DatasetVersion("synthetic-canonical-v0.1"),
        feature_set_version=INITIAL_FEATURE_SET.feature_set_version,
        created_at=datetime(2026, 8, 10, 9, 30, tzinfo=UTC),
        source_canonical_content_sha256=source_checksum,
        feature_definition_sha256=initial_feature_definition_sha256(),
    )


def test_feature_snapshot_is_immutable_reloadable_and_idempotent(tmp_path: Path) -> None:
    values = compute_initial_feature_frame(_bars(220))
    store = FeatureSnapshotStore(tmp_path)

    first = store.promote(values, _request())
    second = store.promote(values, _request())

    assert first == second
    assert first.record_count == 220 * len(INITIAL_FEATURE_SET.definitions)
    assert first.available_count > 0
    assert first.warmup_count > 0
    assert first.input_unavailable_count == 0
    assert store.load(
        DatasetVersion("synthetic-canonical-v0.1"),
        INITIAL_FEATURE_SET.feature_set_version,
    ) == values


def test_same_snapshot_identity_rejects_different_provenance(tmp_path: Path) -> None:
    values = compute_initial_feature_frame(_bars(220))
    store = FeatureSnapshotStore(tmp_path)
    store.promote(values, _request())

    with pytest.raises(FeatureSnapshotConflictError, match="different content or provenance"):
        store.promote(values, _request(source_checksum="b" * 64))
