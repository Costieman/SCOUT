from datetime import date

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.providers.eodhd_daily_update import assess_eodhd_daily_update

V1 = DatasetVersion("eodhd-daily-v1")
V2 = DatasetVersion("eodhd-daily-v2")


def _bar(
    trade_date: date,
    *,
    close: float,
    version: DatasetVersion,
    provider_id: str = "eodhd",
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId("tsi-eodhd-test"),
        trade_date=trade_date,
        open_raw=close,
        high_raw=close + 1.0,
        low_raw=close - 1.0,
        close_raw=close,
        volume_raw=1_000_000,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close + 1.0,
        low_split_adjusted=close - 1.0,
        close_split_adjusted=close,
        provider_id=provider_id,
        dataset_version=version,
        quality_status=QualityStatus.PASS,
    )


def test_eodhd_update_summarizes_append_and_correction() -> None:
    base = (
        _bar(date(2026, 8, 6), close=100.0, version=V1),
        _bar(date(2026, 8, 7), close=101.0, version=V1),
    )
    incoming = (
        _bar(date(2026, 8, 7), close=101.5, version=V2),
        _bar(date(2026, 8, 8), close=102.0, version=V2),
    )

    evidence = assess_eodhd_daily_update(
        base,
        incoming,
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    assert evidence.parent_dataset_version == V1
    assert evidence.target_dataset_version == V2
    assert evidence.incoming_count == 2
    assert evidence.added_count == 1
    assert evidence.revised_count == 1
    assert evidence.unchanged_incoming_count == 0
    assert evidence.carried_forward_count == 1
    assert evidence.requires_new_version is True


def test_eodhd_update_records_idempotent_overlap() -> None:
    base = (_bar(date(2026, 8, 7), close=101.0, version=V1),)
    incoming = (_bar(date(2026, 8, 7), close=101.0, version=V2),)

    evidence = assess_eodhd_daily_update(
        base,
        incoming,
        target_dataset_version=V2,
        correction_window_start=date(2026, 8, 6),
    )

    assert evidence.added_count == 0
    assert evidence.revised_count == 0
    assert evidence.unchanged_incoming_count == 1
    assert evidence.requires_new_version is False


def test_eodhd_update_rejects_non_eodhd_bars() -> None:
    base = (_bar(date(2026, 8, 7), close=101.0, version=V1),)
    incoming = (
        _bar(
            date(2026, 8, 8),
            close=102.0,
            version=V2,
            provider_id="other",
        ),
    )

    with pytest.raises(ValueError, match="provider_id='eodhd'"):
        assess_eodhd_daily_update(
            base,
            incoming,
            target_dataset_version=V2,
            correction_window_start=date(2026, 8, 6),
        )
