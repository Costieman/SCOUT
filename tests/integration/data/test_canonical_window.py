from datetime import UTC, date, datetime, timedelta

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, DatasetPromotionRequest
from trade_scout.data.canonical_window import CanonicalDailyBarWindowReader
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus

VERSION = DatasetVersion("canonical-window-test-v1")


def _bar(instrument_id: str, offset: int) -> DailyBar:
    trade_date = date(2026, 1, 1) + timedelta(days=offset)
    close = 100.0 + offset
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=close,
        high_raw=close + 1.0,
        low_raw=close - 1.0,
        close_raw=close,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close + 1.0,
        low_split_adjusted=close - 1.0,
        close_split_adjusted=close,
        provider_id="primary",
        dataset_version=VERSION,
        quality_status=QualityStatus.PASS,
    )


def _request() -> DatasetPromotionRequest:
    return DatasetPromotionRequest(
        dataset_id="equities_daily",
        dataset_version=VERSION,
        primary_provider_id="primary",
        created_at=datetime(2026, 1, 20, tzinfo=UTC),
        source_batch_ids=("window-test",),
        transformation_version="daily-bars-v0.1",
        adjustment_policy_version="split-only-v0.1",
        universe_construction_version="test-v0.1",
        quality_check_version="test-v0.1",
    )


def test_window_reader_filters_instruments_dates_and_exact_warmup(tmp_path) -> None:
    bars = tuple(
        _bar(instrument_id, offset) for instrument_id in ("tsi_1", "tsi_2") for offset in range(10)
    )
    CanonicalDailyBarStore(tmp_path).promote(bars, _request())
    reader = CanonicalDailyBarWindowReader(tmp_path, VERSION)

    selected = reader.load_window(
        instrument_ids=("tsi_1",),
        signal_start=date(2026, 1, 6),
        signal_end=date(2026, 1, 8),
        warmup_observations=3,
    )

    assert reader.manifest_record_count() == 20
    assert reader.latest_trade_date() == date(2026, 1, 10)
    assert {str(item.instrument_id) for item in selected} == {"tsi_1"}
    assert tuple(item.trade_date for item in selected) == tuple(
        date(2026, 1, day) for day in range(3, 9)
    )
