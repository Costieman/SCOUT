from datetime import date

from trade_scout.data.session_completeness import (
    US_EQUITY_SESSION_CALENDAR_VERSION,
    default_us_equity_session_calendar,
    expected_exchange_sessions,
)


def test_bats_uses_pinned_us_equity_full_day_calendar() -> None:
    calendar = default_us_equity_session_calendar()

    assert calendar.definition_version == US_EQUITY_SESSION_CALENDAR_VERSION
    assert "BATS" in calendar.supported_exchanges
    assert any("cboe.com" in ref for ref in calendar.evidence_refs)
    assert expected_exchange_sessions(
        exchange="BATS",
        start=date(2026, 4, 2),
        end=date(2026, 4, 6),
        calendar=calendar,
    ) == (date(2026, 4, 2), date(2026, 4, 6))
