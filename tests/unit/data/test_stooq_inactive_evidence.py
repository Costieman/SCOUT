from datetime import date

from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.providers.stooq_inactive_evidence import (
    StooqInactiveEvidenceState,
    characterize_stooq_inactive_history,
)


def _bar(day: date, close: float = 10.0) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="stooq",
        provider_instrument_id="evidence-id",
        symbol="OLD.US",
        trade_date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        split_factor=None,
        dividend_cash=None,
    )


def test_inactive_history_with_aligned_terminal_date() -> None:
    evidence = characterize_stooq_inactive_history(
        (_bar(date(2019, 12, 30)), _bar(date(2020, 1, 2))),
        symbol="OLD.US",
        expected_terminal_date=date(2020, 1, 3),
        terminal_tolerance_days=3,
    )

    assert evidence.state is StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_ALIGNED
    assert evidence.observation_count == 2
    assert evidence.terminal_date_error_days == 1


def test_inactive_history_reports_terminal_mismatch() -> None:
    evidence = characterize_stooq_inactive_history(
        (_bar(date(2019, 11, 1)),),
        symbol="OLD.US",
        expected_terminal_date=date(2020, 1, 3),
        terminal_tolerance_days=5,
    )

    assert evidence.state is StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_MISMATCH
    assert evidence.terminal_date_error_days == 63


def test_inactive_history_reports_no_history_without_inference() -> None:
    evidence = characterize_stooq_inactive_history(
        (),
        symbol="OLD.US",
        expected_terminal_date=date(2020, 1, 3),
    )

    assert evidence.state is StooqInactiveEvidenceState.NO_HISTORY
    assert evidence.observation_count == 0
    assert "does not prove why" in evidence.note


def test_inactive_history_without_terminal_fact_is_inconclusive() -> None:
    evidence = characterize_stooq_inactive_history(
        (_bar(date(2019, 11, 1)),),
        symbol="OLD.US",
        expected_terminal_date=None,
    )

    assert evidence.state is StooqInactiveEvidenceState.INCONCLUSIVE
    assert evidence.last_trade_date == date(2019, 11, 1)
