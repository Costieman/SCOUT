from datetime import UTC, date, datetime

import pytest

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetIntegrityError,
    DatasetPromotionQualityError,
    DatasetPromotionRequest,
    DatasetVersionConflictError,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus

VERSION = DatasetVersion("equities_daily_v0.1.0")


def _bar(
    *,
    instrument_id: str = "tsi_1",
    trade_date: date = date(2026, 8, 6),
    close: float = 103.0,
    quality_status: QualityStatus = QualityStatus.PASS,
    provider_id: str = "primary",
    dataset_version: DatasetVersion = VERSION,
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=100.0,
        high_raw=105.0,
        low_raw=99.0,
        close_raw=close,
        volume_raw=1_000_000,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=100.0,
        high_split_adjusted=105.0,
        low_split_adjusted=99.0,
        close_split_adjusted=close,
        provider_id=provider_id,
        dataset_version=dataset_version,
        quality_status=quality_status,
    )


def _request(*, created_at: datetime | None = None) -> DatasetPromotionRequest:
    return DatasetPromotionRequest(
        dataset_id="equities_daily",
        dataset_version=VERSION,
        primary_provider_id="primary",
        created_at=created_at or datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        source_batch_ids=("batch-001", "batch-002"),
        transformation_version="daily-bars-v0.1.0",
        adjustment_policy_version="equity-adjustment-v0.1.0",
        universe_construction_version="us-equity-v0.1.0",
        quality_check_version="daily-bar-quality-v0.1.0",
    )


def test_promote_round_trips_parquet_and_manifest(tmp_path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    bars = (
        _bar(instrument_id="tsi_2", trade_date=date(2026, 8, 7), close=104.0),
        _bar(instrument_id="tsi_1", trade_date=date(2026, 8, 6), close=103.0),
    )

    manifest = store.promote(bars, _request())

    assert manifest.record_count == 2
    assert manifest.quality_summary.pass_count == 2
    assert manifest.first_trade_date == date(2026, 8, 6)
    assert manifest.last_trade_date == date(2026, 8, 7)
    assert (tmp_path / manifest.parquet_relative_path).is_file()
    assert (tmp_path / "metadata" / "datasets.duckdb").is_file()
    assert store.get_manifest(VERSION) == manifest
    assert store.load(VERSION) == tuple(sorted(bars, key=lambda bar: str(bar.instrument_id)))


def test_identical_promotion_is_idempotent(tmp_path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    request = _request()
    first = store.promote((_bar(),), request)
    parquet_path = tmp_path / first.parquet_relative_path
    original_bytes = parquet_path.read_bytes()

    second = store.promote((_bar(),), request)

    assert second == first
    assert parquet_path.read_bytes() == original_bytes


def test_dataset_version_cannot_be_reused_for_different_content(tmp_path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    store.promote((_bar(),), _request())

    with pytest.raises(DatasetVersionConflictError):
        store.promote((_bar(close=102.0),), _request())


def test_quarantined_records_cannot_be_promoted(tmp_path) -> None:
    store = CanonicalDailyBarStore(tmp_path)

    with pytest.raises(DatasetPromotionQualityError):
        store.promote((_bar(quality_status=QualityStatus.QUARANTINE),), _request())


def test_provider_and_dataset_version_must_match_promotion_request(tmp_path) -> None:
    store = CanonicalDailyBarStore(tmp_path)

    with pytest.raises(DatasetVersionConflictError):
        store.promote((_bar(provider_id="other"),), _request())

    with pytest.raises(DatasetVersionConflictError):
        store.promote(
            (_bar(dataset_version=DatasetVersion("equities_daily_v0.2.0")),),
            _request(),
        )


def test_tampered_parquet_is_detected_before_read(tmp_path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    manifest = store.promote((_bar(),), _request())
    parquet_path = tmp_path / manifest.parquet_relative_path
    parquet_path.write_bytes(parquet_path.read_bytes() + b"tampered")

    with pytest.raises(CanonicalDatasetIntegrityError):
        store.load(VERSION)


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _request(created_at=datetime(2026, 8, 8, 12, 0))
