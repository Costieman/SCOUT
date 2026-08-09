from datetime import date
import json

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.providers.eodhd_daily_update import assess_eodhd_daily_update
from trade_scout.data.providers.eodhd_daily_update_report import write_eodhd_daily_update_report


def _bar(trade_date: date, *, version: str, close: float) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId("tsi-1"),
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
        provider_id="eodhd",
        dataset_version=DatasetVersion(version),
        quality_status=QualityStatus.PASS,
    )


def test_report_records_live_provenance_and_revision_counts(tmp_path) -> None:
    evidence = assess_eodhd_daily_update(
        (
            _bar(date(2026, 8, 7), version="v1", close=100.0),
            _bar(date(2026, 8, 8), version="v1", close=101.0),
        ),
        (
            _bar(date(2026, 8, 8), version="v2", close=101.5),
            _bar(date(2026, 8, 9), version="v2", close=102.0),
        ),
        target_dataset_version=DatasetVersion("v2"),
        correction_window_start=date(2026, 8, 7),
    )

    path = write_eodhd_daily_update_report(
        evidence,
        path=tmp_path / "daily-update.json",
        live_provider_observation=True,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "eodhd-daily-update-evidence-v0.1"
    assert payload["provider_id"] == "eodhd"
    assert payload["live_provider_observation"] is True
    assert payload["added_count"] == 1
    assert payload["revised_count"] == 1
    assert payload["change_count"] == 2
    assert payload["requires_new_version"] is True


def test_report_does_not_confuse_synthetic_evidence_with_live_provider_evidence(tmp_path) -> None:
    evidence = assess_eodhd_daily_update(
        (_bar(date(2026, 8, 8), version="v1", close=101.0),),
        (_bar(date(2026, 8, 8), version="v2", close=101.0),),
        target_dataset_version=DatasetVersion("v2"),
        correction_window_start=date(2026, 8, 8),
    )

    path = write_eodhd_daily_update_report(
        evidence,
        path=tmp_path / "synthetic.json",
        live_provider_observation=False,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["live_provider_observation"] is False
    assert payload["unchanged_incoming_count"] == 1
    assert payload["change_count"] == 0
    assert payload["requires_new_version"] is False
