from __future__ import annotations

from datetime import UTC, date, datetime

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, DatasetPromotionRequest
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    QualityStatus,
    SecurityType,
)
from trade_scout.data.eodhd_campaign_benchmark import assess_and_benchmark_eodhd_campaign
from trade_scout.data.representative_sample import RepresentativeSamplePolicy


def _bar(instrument_id: str, trade_date: date, version: DatasetVersion) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=10.0,
        high_raw=11.0,
        low_raw=9.0,
        close_raw=10.5,
        volume_raw=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=10.0,
        high_split_adjusted=11.0,
        low_split_adjusted=9.0,
        close_split_adjusted=10.5,
        provider_id="eodhd",
        dataset_version=version,
        quality_status=QualityStatus.PASS,
    )


def _instrument(instrument_id: str) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol=instrument_id,
        name=instrument_id,
        exchange="NYSE",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=date(2010, 1, 1),
        delisting_date=None,
        provider_ids={"eodhd": instrument_id},
    )


def _promote(root, version: DatasetVersion) -> None:
    CanonicalDailyBarStore(root).promote(
        (_bar("AAA", date(2020, 1, 2), version), _bar("AAA", date(2020, 1, 3), version)),
        DatasetPromotionRequest(
            dataset_id="campaign",
            dataset_version=version,
            primary_provider_id="eodhd",
            created_at=datetime(2026, 8, 9, tzinfo=UTC),
            source_batch_ids=("raw-1",),
            transformation_version="normalization-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="campaign-v1",
            quality_check_version="quality-v1",
        ),
    )


def test_nonrepresentative_campaign_is_not_benchmarked(tmp_path) -> None:
    version = DatasetVersion("sample-v1")
    source = tmp_path / "source"
    _promote(source, version)
    evidence = assess_and_benchmark_eodhd_campaign(
        source_root=source,
        dataset_version=version,
        instruments=(_instrument("AAA"),),
        policy=RepresentativeSamplePolicy(
            version="policy-v1",
            min_record_count=10,
            min_unique_instruments=1,
            min_span_days=0,
            min_delisted_instruments=0,
            min_exchanges=1,
        ),
        benchmark_root=tmp_path / "benchmark",
        query_start=date(2020, 1, 2),
        query_end=date(2020, 1, 3),
    )

    assert evidence.representative_sample_accepted is False
    assert evidence.storage_benchmark is None
    assert "record_count_below_minimum" in evidence.representative_sample.failures


def test_representative_campaign_runs_registered_dataset_benchmark(tmp_path) -> None:
    version = DatasetVersion("sample-v1")
    source = tmp_path / "source"
    _promote(source, version)
    evidence = assess_and_benchmark_eodhd_campaign(
        source_root=source,
        dataset_version=version,
        instruments=(_instrument("AAA"),),
        policy=RepresentativeSamplePolicy(
            version="policy-v1",
            min_record_count=2,
            min_unique_instruments=1,
            min_span_days=1,
            min_delisted_instruments=0,
            min_exchanges=1,
        ),
        benchmark_root=tmp_path / "benchmark",
        query_start=date(2020, 1, 2),
        query_end=date(2020, 1, 3),
    )

    assert evidence.representative_sample_accepted is True
    assert evidence.storage_benchmark is not None
    assert evidence.storage_benchmark.record_count == 2
    assert evidence.storage_benchmark.filtered_query_count == 2
