from datetime import date

import pytest

from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.targeted_gap_validation import (
    TargetedGapCase,
    TargetedGapValidationError,
    evaluate_targeted_gap_validator,
    expected_target_gap_sessions,
)


def _case() -> TargetedGapCase:
    return TargetedGapCase(
        case_id="algn-tiingo-initial-coverage-gap-v0.1",
        symbol="ALGN",
        exchange="XNAS",
        lifecycle_start_date=date(2001, 1, 26),
        observed_provider_id="tiingo",
        observed_first_date=date(2001, 1, 30),
        validator_provider_id="alpha_vantage",
        validator_symbol="ALGN",
        anchor_date=date(2001, 1, 30),
        evidence_refs=("https://www.sec.gov/example",),
    )


def _bar(
    day: date, *, provider_id: str = "alpha_vantage", symbol: str = "ALGN"
) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id=provider_id,
        provider_instrument_id=f"{provider_id}:symbol:{symbol}",
        symbol=symbol,
        trade_date=day,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=1000.0,
    )


def test_algn_gap_sessions_are_derived_from_pinned_exchange_calendar() -> None:
    assert expected_target_gap_sessions(_case()) == (
        date(2001, 1, 26),
        date(2001, 1, 29),
    )


def test_validator_presence_requires_both_gap_sessions_and_overlap_anchor() -> None:
    result = evaluate_targeted_gap_validator(
        _case(),
        (
            _bar(date(2001, 1, 26)),
            _bar(date(2001, 1, 29)),
            _bar(date(2001, 1, 30)),
        ),
    )

    assert result.validator_present_gap_sessions == (
        date(2001, 1, 26),
        date(2001, 1, 29),
    )
    assert result.validator_missing_gap_sessions == ()
    assert result.validator_anchor_present is True
    assert result.gap_fully_observed_by_validator is True
    assert result.ready_for_manual_adjudication is True


def test_missing_anchor_or_gap_session_remains_inconclusive() -> None:
    no_anchor = evaluate_targeted_gap_validator(
        _case(),
        (_bar(date(2001, 1, 26)), _bar(date(2001, 1, 29))),
    )
    missing_gap = evaluate_targeted_gap_validator(
        _case(),
        (_bar(date(2001, 1, 26)), _bar(date(2001, 1, 30))),
    )

    assert no_anchor.gap_fully_observed_by_validator is True
    assert no_anchor.ready_for_manual_adjudication is False
    assert missing_gap.validator_missing_gap_sessions == (date(2001, 1, 29),)
    assert missing_gap.ready_for_manual_adjudication is False


def test_validator_rejects_provider_symbol_and_duplicate_session_mismatches() -> None:
    with pytest.raises(TargetedGapValidationError, match="provider mismatch"):
        evaluate_targeted_gap_validator(
            _case(),
            (_bar(date(2001, 1, 26), provider_id="stooq"),),
        )
    with pytest.raises(TargetedGapValidationError, match="symbol mismatch"):
        evaluate_targeted_gap_validator(
            _case(),
            (_bar(date(2001, 1, 26), symbol="WRONG"),),
        )
    with pytest.raises(TargetedGapValidationError, match="duplicate validator session"):
        evaluate_targeted_gap_validator(
            _case(),
            (_bar(date(2001, 1, 26)), _bar(date(2001, 1, 26))),
        )
