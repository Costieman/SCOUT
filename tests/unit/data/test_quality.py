from datetime import date

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.quality import QualityRule, validate_daily_bars


def _bar(**overrides: object) -> DailyBar:
    values: dict[str, object] = {
        "instrument_id": InstrumentId("inst-1"),
        "trade_date": date(2026, 8, 7),
        "open_raw": 100.0,
        "high_raw": 105.0,
        "low_raw": 99.0,
        "close_raw": 103.0,
        "volume_raw": 1_000_000,
        "split_factor": 1.0,
        "dividend_cash": 0.0,
        "open_split_adjusted": 100.0,
        "high_split_adjusted": 105.0,
        "low_split_adjusted": 99.0,
        "close_split_adjusted": 103.0,
        "provider_id": "test-provider",
        "dataset_version": DatasetVersion("equities_daily_v0.1.0"),
        "quality_status": QualityStatus.PASS,
    }
    values.update(overrides)
    return DailyBar(**values)  # type: ignore[arg-type]


def test_clean_batch_passes() -> None:
    report = validate_daily_bars([_bar()])

    assert report.status is QualityStatus.PASS
    assert report.record_count == 1
    assert report.issues == ()


def test_duplicate_instrument_date_is_rejected() -> None:
    bar = _bar()

    report = validate_daily_bars([bar, bar])

    assert report.status is QualityStatus.REJECT
    assert any(issue.rule is QualityRule.DUPLICATE_INSTRUMENT_DATE for issue in report.issues)


def test_impossible_ohlc_is_quarantined_or_rejected_without_repair() -> None:
    original = _bar(high_raw=101.0, close_raw=103.0)

    report = validate_daily_bars([original])

    assert report.status is QualityStatus.QUARANTINE
    assert [issue.rule for issue in report.issues] == [QualityRule.CLOSE_OUTSIDE_RANGE]
    assert original.close_raw == 103.0


def test_negative_price_is_rejected() -> None:
    report = validate_daily_bars([_bar(low_raw=-1.0)])

    assert report.status is QualityStatus.REJECT
    assert any(issue.rule is QualityRule.NEGATIVE_PRICE for issue in report.issues)
