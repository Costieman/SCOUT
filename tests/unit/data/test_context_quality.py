from datetime import date
from types import MappingProxyType

import pytest

from trade_scout.data.context_quality import (
    CoveragePolicy,
    CrossSectionExpectation,
    PriceJumpPolicy,
    validate_completeness,
    validate_corporate_action_price_jumps,
    validate_cross_section_counts,
)
from trade_scout.data.contracts import (
    CorporateActionRecord,
    CorporateActionType,
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)

VERSION = DatasetVersion("equities_daily_v0.1.0")


def _bar(
    instrument_id: str,
    trade_date: date,
    *,
    close: float = 100.0,
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
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
        provider_id="primary",
        dataset_version=VERSION,
        quality_status=QualityStatus.PASS,
    )


def _action(instrument_id: str, effective_date: date) -> CorporateActionRecord:
    return CorporateActionRecord(
        action_id="action-1",
        instrument_id=InstrumentId(instrument_id),
        action_type=CorporateActionType.SPLIT,
        effective_date=effective_date,
        provider_id="primary",
        source_event_id="provider-action-1",
        source_fields=MappingProxyType({}),
    )


def test_completeness_reports_missing_expected_pairs_without_filling() -> None:
    session = date(2026, 8, 7)
    expected = {
        session: frozenset({InstrumentId("tsi-1"), InstrumentId("tsi-2")}),
    }

    report = validate_completeness(
        [_bar("tsi-1", session)],
        expected_instruments_by_session=expected,
        policy=CoveragePolicy(
            warn_missing_fraction=0.0,
            quarantine_missing_fraction=0.75,
        ),
    )

    assert report.status is QualityStatus.WARN
    assert report.expected_count == 2
    assert report.observed_expected_count == 1
    assert report.missing_fraction == 0.5
    assert [(item.instrument_id, item.trade_date) for item in report.missing] == [
        (InstrumentId("tsi-2"), session)
    ]


def test_completeness_can_quarantine_material_coverage_loss() -> None:
    session = date(2026, 8, 7)
    expected = {
        session: frozenset(
            {
                InstrumentId("tsi-1"),
                InstrumentId("tsi-2"),
                InstrumentId("tsi-3"),
                InstrumentId("tsi-4"),
            }
        )
    }

    report = validate_completeness(
        [_bar("tsi-1", session)],
        expected_instruments_by_session=expected,
        policy=CoveragePolicy(
            warn_missing_fraction=0.10,
            quarantine_missing_fraction=0.50,
        ),
    )

    assert report.status is QualityStatus.QUARANTINE
    assert report.missing_count == 3


def test_cross_section_counts_use_explicit_historical_ranges() -> None:
    first = date(2026, 8, 6)
    second = date(2026, 8, 7)
    bars = [
        _bar("tsi-1", first),
        _bar("tsi-2", first),
        _bar("tsi-1", second),
    ]

    report = validate_cross_section_counts(
        bars,
        expectations=(
            CrossSectionExpectation(first, minimum_count=2, maximum_count=3),
            CrossSectionExpectation(second, minimum_count=2, maximum_count=3),
        ),
        out_of_range_status=QualityStatus.QUARANTINE,
    )

    assert report.status is QualityStatus.QUARANTINE
    assert report.sessions[0].status is QualityStatus.PASS
    assert report.sessions[1].observed_count == 1
    assert report.sessions[1].status is QualityStatus.QUARANTINE


def test_unexplained_large_raw_price_jump_is_flagged() -> None:
    bars = [
        _bar("tsi-1", date(2026, 8, 6), close=100.0),
        _bar("tsi-1", date(2026, 8, 7), close=50.0),
    ]

    report = validate_corporate_action_price_jumps(
        bars,
        corporate_actions=(),
        policy=PriceJumpPolicy(
            absolute_return_threshold=0.25,
            unexplained_status=QualityStatus.QUARANTINE,
        ),
    )

    assert report.status is QualityStatus.QUARANTINE
    assert len(report.anomalies) == 1
    assert report.anomalies[0].raw_return == -0.5


def test_recorded_action_prevents_jump_from_being_called_unexplained() -> None:
    bars = [
        _bar("tsi-1", date(2026, 8, 6), close=100.0),
        _bar("tsi-1", date(2026, 8, 7), close=50.0),
    ]

    report = validate_corporate_action_price_jumps(
        bars,
        corporate_actions=(_action("tsi-1", date(2026, 8, 7)),),
        policy=PriceJumpPolicy(
            absolute_return_threshold=0.25,
            unexplained_status=QualityStatus.QUARANTINE,
        ),
    )

    assert report.status is QualityStatus.PASS
    assert report.anomalies == ()


def test_action_between_non_adjacent_trading_dates_is_recognized() -> None:
    bars = [
        _bar("tsi-1", date(2026, 8, 7), close=100.0),
        _bar("tsi-1", date(2026, 8, 10), close=50.0),
    ]

    report = validate_corporate_action_price_jumps(
        bars,
        corporate_actions=(_action("tsi-1", date(2026, 8, 9)),),
        policy=PriceJumpPolicy(
            absolute_return_threshold=0.25,
            unexplained_status=QualityStatus.WARN,
        ),
    )

    assert report.status is QualityStatus.PASS


def test_quality_threshold_policies_must_be_explicit_and_valid() -> None:
    with pytest.raises(ValueError):
        CoveragePolicy(warn_missing_fraction=0.5, quarantine_missing_fraction=0.25)

    with pytest.raises(ValueError):
        PriceJumpPolicy(
            absolute_return_threshold=0.0,
            unexplained_status=QualityStatus.WARN,
        )

    with pytest.raises(ValueError):
        validate_cross_section_counts(
            (),
            expectations=(),
            out_of_range_status=QualityStatus.PASS,
        )
