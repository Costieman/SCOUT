import json
from datetime import date
from types import MappingProxyType

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    QualityStatus,
    SecurityType,
)
from trade_scout.data.session_completeness import (
    US_EQUITY_SESSION_CALENDAR_VERSION,
    audit_daily_bar_session_completeness,
    default_us_equity_session_calendar,
    expected_exchange_sessions,
    persist_session_completeness_report,
)

_DATASET_VERSION = DatasetVersion("test-reviewed-v0.1")
_INSTRUMENT_ID = InstrumentId("tsi_session_test")


def _instrument(
    *,
    exchange: str = "XNAS",
    first_trade_date: date | None = None,
    delisting_date: date | None = None,
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=_INSTRUMENT_ID,
        primary_symbol="TEST",
        name="Test Corp",
        exchange=exchange,
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=first_trade_date,
        delisting_date=delisting_date,
        provider_ids=MappingProxyType({"review": "test"}),
    )


def _bar(day: date) -> DailyBar:
    return DailyBar(
        instrument_id=_INSTRUMENT_ID,
        trade_date=day,
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
        provider_id="test-provider",
        dataset_version=_DATASET_VERSION,
        quality_status=QualityStatus.PASS,
    )


def test_expected_sessions_apply_regular_holidays_and_new_year_saturday_rule() -> None:
    sessions = expected_exchange_sessions(
        exchange="XNYS",
        start=date(2021, 12, 31),
        end=date(2022, 1, 3),
    )

    assert sessions == (date(2021, 12, 31), date(2022, 1, 3))
    assert date(2026, 4, 3) not in expected_exchange_sessions(
        exchange="XNAS",
        start=date(2026, 4, 2),
        end=date(2026, 4, 6),
    )
    assert date(2022, 6, 20) not in expected_exchange_sessions(
        exchange="XNYS",
        start=date(2022, 6, 17),
        end=date(2022, 6, 21),
    )


def test_expected_sessions_apply_sourced_exceptional_full_day_closures() -> None:
    calendar = default_us_equity_session_calendar()

    assert calendar.definition_version == US_EQUITY_SESSION_CALENDAR_VERSION
    assert expected_exchange_sessions(
        exchange="XNAS",
        start=date(2001, 9, 10),
        end=date(2001, 9, 17),
        calendar=calendar,
    ) == (date(2001, 9, 10), date(2001, 9, 17))
    assert expected_exchange_sessions(
        exchange="XNYS",
        start=date(2012, 10, 26),
        end=date(2012, 10, 31),
        calendar=calendar,
    ) == (date(2012, 10, 26), date(2012, 10, 31))
    for closure in (
        date(2004, 6, 11),
        date(2007, 1, 2),
        date(2018, 12, 5),
        date(2025, 1, 9),
    ):
        assert closure not in expected_exchange_sessions(
            exchange="XNYS",
            start=closure,
            end=closure,
            calendar=calendar,
        )


def test_audit_detects_internal_and_terminal_missing_sessions() -> None:
    audit = audit_daily_bar_session_completeness(
        (_bar(date(2024, 1, 2)), _bar(date(2024, 1, 4))),
        instruments=(_instrument(),),
        dataset_end_date=date(2024, 1, 5),
    )

    instrument = audit.instruments[0]
    assert instrument.missing_expected_sessions == (date(2024, 1, 3), date(2024, 1, 5))
    assert audit.missing_expected_session_count == 2
    assert audit.unexpected_observed_date_count == 0
    assert audit.complete is False


def test_audit_detects_unexpected_non_session_bar_without_fabricating_data() -> None:
    audit = audit_daily_bar_session_completeness(
        (_bar(date(2024, 1, 1)), _bar(date(2024, 1, 2))),
        instruments=(_instrument(),),
        dataset_end_date=date(2024, 1, 2),
    )

    instrument = audit.instruments[0]
    assert instrument.missing_expected_sessions == ()
    assert instrument.unexpected_observed_dates == (date(2024, 1, 1),)
    assert audit.complete is False


def test_first_trade_and_delisting_bounds_are_respected() -> None:
    instrument = _instrument(
        first_trade_date=date(2024, 1, 3),
        delisting_date=date(2024, 1, 4),
    )
    audit = audit_daily_bar_session_completeness(
        (_bar(date(2024, 1, 3)), _bar(date(2024, 1, 4))),
        instruments=(instrument,),
        dataset_end_date=date(2024, 1, 5),
    )

    result = audit.instruments[0]
    assert result.expected_start_date == date(2024, 1, 3)
    assert result.expected_end_date == date(2024, 1, 4)
    assert result.complete is True
    assert audit.complete is True


def test_metadata_report_contains_dates_and_counts_but_no_price_values(tmp_path) -> None:
    audit = audit_daily_bar_session_completeness(
        (_bar(date(2024, 1, 2)), _bar(date(2024, 1, 3))),
        instruments=(_instrument(),),
        dataset_end_date=date(2024, 1, 3),
    )
    path = tmp_path / "session-completeness.json"

    persist_session_completeness_report(
        path,
        audit,
        source_canonical_content_sha256="a" * 64,
        identity_snapshot_version="identity-v0.1",
    )

    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["complete"] is True
    assert payload["missing_expected_session_count"] == 0
    assert payload["bars_fabricated"] == 0
    assert payload["provider_calls_made"] is False
    assert "open_raw" not in text
    assert "close_raw" not in text
    assert "10.5" not in text
