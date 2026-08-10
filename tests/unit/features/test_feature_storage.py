from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)
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

_DATASET = DatasetVersion("synthetic-canonical-v0.1")


def _bars(count: int) -> tuple[DailyBar, ...]:
    start = date(2020, 1, 1)
    result: list[DailyBar] = []
    for index in range(count):
        close = 100.0 + index
        result.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_feature_storage_test"),
                trade_date=start + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=1000.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=_DATASET,
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(result)


def _request(*, source_checksum: str = "a" * 64) -> FeatureSnapshotPromotionRequest:
    return FeatureSnapshotPromotionRequest(
        dataset_version=_DATASET,
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
    assert store.load(_DATASET, INITIAL_FEATURE_SET.feature_set_version) == values

    snapshot_dir = (
        tmp_path / "derived" / "features" / str(_DATASET) / INITIAL_FEATURE_SET.feature_set_version
    )
    assert {item.name for item in snapshot_dir.iterdir()} == {"features.parquet"}


def test_same_snapshot_identity_rejects_different_provenance(tmp_path: Path) -> None:
    values = compute_initial_feature_frame(_bars(220))
    store = FeatureSnapshotStore(tmp_path)
    store.promote(values, _request())

    with pytest.raises(FeatureSnapshotConflictError, match="different content or provenance"):
        store.promote(values, _request(source_checksum="b" * 64))
