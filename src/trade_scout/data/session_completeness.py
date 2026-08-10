"""Deterministic expected-session completeness checks for canonical U.S. equity bars."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, InstrumentRecord

US_EQUITY_SESSION_CALENDAR_VERSION = "us-equities-core-full-day-v0.1"
_SUPPORTED_EXCHANGES = frozenset({"XNYS", "XNAS"})
_SEC_911_URL = (
    "https://www.sec.gov/rules-regulations/2001/09/"
    "emergency-order-pursuant-section-12k2-securities-exchange-act-1934-"
    "taking-temporary-action-respond"
)
_NYSE_HOLIDAY_URL = "https://www.nyse.com/markets/hours-calendars"
_NASDAQ_STATUS_URL = "https://www.nasdaqtrader.com/Trader.aspx?id=MarketSystemStatusSearch"


class SessionCompletenessError(RuntimeError):
    """Raised when a session audit cannot be evaluated deterministically."""


@dataclass(frozen=True, slots=True)
class ExceptionalClosure:
    """One sourced full-day U.S. equity market closure outside recurring holiday rules."""

    trade_date: date
    label: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExchangeSessionCalendar:
    """Versioned full-day calendar policy for supported U.S. equity exchanges."""

    definition_version: str
    supported_exchanges: frozenset[str]
    exceptional_closures: Mapping[date, ExceptionalClosure]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstrumentSessionCompleteness:
    """Expected-versus-observed daily-session result for one permanent instrument identity."""

    instrument_id: InstrumentId
    exchange: str
    expected_start_date: date | None
    expected_end_date: date
    observed_first_date: date | None
    observed_last_date: date | None
    observed_bar_count: int
    distinct_observed_date_count: int
    expected_session_count: int
    duplicate_observed_date_count: int
    missing_history: bool
    missing_expected_sessions: tuple[date, ...]
    unexpected_observed_dates: tuple[date, ...]

    @property
    def complete(self) -> bool:
        """Return whether no expected-session or lifecycle defect was observed."""

        return not (
            self.missing_history
            or self.duplicate_observed_date_count
            or self.missing_expected_sessions
            or self.unexpected_observed_dates
        )


@dataclass(frozen=True, slots=True)
class DatasetSessionCompletenessAudit:
    """Dataset-wide expected-session completeness result."""

    dataset_version: DatasetVersion
    calendar_definition_version: str
    dataset_end_date: date
    instruments: tuple[InstrumentSessionCompleteness, ...]

    @property
    def instrument_count(self) -> int:
        return len(self.instruments)

    @property
    def complete_instrument_count(self) -> int:
        return sum(item.complete for item in self.instruments)

    @property
    def missing_history_instrument_count(self) -> int:
        return sum(item.missing_history for item in self.instruments)

    @property
    def missing_expected_session_count(self) -> int:
        return sum(len(item.missing_expected_sessions) for item in self.instruments)

    @property
    def unexpected_observed_date_count(self) -> int:
        return sum(len(item.unexpected_observed_dates) for item in self.instruments)

    @property
    def duplicate_observed_date_count(self) -> int:
        return sum(item.duplicate_observed_date_count for item in self.instruments)

    @property
    def expected_session_observation_count(self) -> int:
        return sum(item.expected_session_count for item in self.instruments)

    @property
    def complete(self) -> bool:
        return all(item.complete for item in self.instruments)


def default_us_equity_session_calendar() -> ExchangeSessionCalendar:
    """Return the pinned 2001+ full-day XNYS/XNAS session policy used by Trade Scout."""

    closures = (
        _closure(date(2001, 9, 11), "September 11 attacks market closure", _SEC_911_URL),
        _closure(date(2001, 9, 12), "September 11 attacks market closure", _SEC_911_URL),
        _closure(date(2001, 9, 13), "September 11 attacks market closure", _SEC_911_URL),
        _closure(date(2001, 9, 14), "September 11 attacks market closure", _SEC_911_URL),
        _closure(
            date(2004, 6, 11),
            "National day of mourning for Ronald Reagan",
            "https://www.sec.gov/news/press/2004-77.htm",
        ),
        _closure(
            date(2007, 1, 2),
            "National day of mourning for Gerald Ford",
            "https://www.nasdaqtrader.com/TraderNews.aspx?id=gn2007-022",
        ),
        _closure(
            date(2012, 10, 29),
            "Hurricane Sandy market closure",
            "https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2012-44",
        ),
        _closure(
            date(2012, 10, 30),
            "Hurricane Sandy market closure",
            "https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2012-45",
        ),
        _closure(
            date(2018, 12, 5),
            "National day of mourning for George H.W. Bush",
            "https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2018-98",
        ),
        _closure(
            date(2025, 1, 9),
            "National day of mourning for Jimmy Carter",
            "https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2024-87",
        ),
    )
    return ExchangeSessionCalendar(
        definition_version=US_EQUITY_SESSION_CALENDAR_VERSION,
        supported_exchanges=_SUPPORTED_EXCHANGES,
        exceptional_closures=MappingProxyType({item.trade_date: item for item in closures}),
        evidence_refs=(_NYSE_HOLIDAY_URL, _NASDAQ_STATUS_URL),
    )


def expected_exchange_sessions(
    *,
    exchange: str,
    start: date,
    end: date,
    calendar: ExchangeSessionCalendar | None = None,
) -> tuple[date, ...]:
    """Return expected full-day sessions, inclusive, for one supported listing exchange."""

    policy = calendar or default_us_equity_session_calendar()
    if exchange not in policy.supported_exchanges:
        raise SessionCompletenessError(f"unsupported exchange session calendar: {exchange}")
    if end < start:
        return ()

    sessions: list[date] = []
    cursor = start
    while cursor <= end:
        if _is_expected_session(cursor, policy):
            sessions.append(cursor)
        cursor += timedelta(days=1)
    return tuple(sessions)


def audit_daily_bar_session_completeness(
    bars: Iterable[DailyBar],
    *,
    instruments: Iterable[InstrumentRecord],
    dataset_end_date: date,
    calendar: ExchangeSessionCalendar | None = None,
) -> DatasetSessionCompletenessAudit:
    """Compare canonical bar dates with expected exchange sessions without inventing bars.

    A reviewed ``first_trade_date`` defines the start when available; otherwise the first observed
    canonical bar does. Active instruments are expected through ``dataset_end_date`` and delisted
    instruments only through their recorded delisting date.
    """

    policy = calendar or default_us_equity_session_calendar()
    materialized = tuple(bars)
    if not materialized:
        raise SessionCompletenessError("session completeness audit requires at least one daily bar")
    versions = {bar.dataset_version for bar in materialized}
    if len(versions) != 1:
        raise SessionCompletenessError("session completeness audit requires one dataset version")
    if any(bar.trade_date > dataset_end_date for bar in materialized):
        raise SessionCompletenessError("dataset_end_date precedes one or more observed bars")
    dataset_version = next(iter(versions))

    instrument_records = tuple(instruments)
    instrument_by_id: dict[InstrumentId, InstrumentRecord] = {}
    for instrument in instrument_records:
        if instrument.instrument_id in instrument_by_id:
            raise SessionCompletenessError(
                f"duplicate instrument record {instrument.instrument_id} in session audit"
            )
        if instrument.exchange not in policy.supported_exchanges:
            raise SessionCompletenessError(
                f"unsupported exchange session calendar: {instrument.exchange}"
            )
        instrument_by_id[instrument.instrument_id] = instrument

    bars_by_instrument: dict[InstrumentId, list[DailyBar]] = {
        instrument_id: [] for instrument_id in instrument_by_id
    }
    for bar in materialized:
        if bar.instrument_id not in bars_by_instrument:
            raise SessionCompletenessError(
                f"canonical bar references unknown instrument {bar.instrument_id}"
            )
        bars_by_instrument[bar.instrument_id].append(bar)

    results = tuple(
        _audit_instrument(
            instrument=instrument,
            bars=tuple(bars_by_instrument[instrument.instrument_id]),
            dataset_end_date=dataset_end_date,
            calendar=policy,
        )
        for instrument in sorted(instrument_records, key=lambda item: str(item.instrument_id))
    )
    return DatasetSessionCompletenessAudit(
        dataset_version=dataset_version,
        calendar_definition_version=policy.definition_version,
        dataset_end_date=dataset_end_date,
        instruments=results,
    )


def persist_session_completeness_report(
    path: Path,
    audit: DatasetSessionCompletenessAudit,
    *,
    source_canonical_content_sha256: str,
    identity_snapshot_version: str,
    calendar: ExchangeSessionCalendar | None = None,
) -> None:
    """Persist metadata-only expected-session evidence without canonical price values."""

    policy = calendar or default_us_equity_session_calendar()
    if policy.definition_version != audit.calendar_definition_version:
        raise SessionCompletenessError("calendar version differs from completed audit")
    payload = {
        "schema_version": "canonical-session-completeness-report-v0.1",
        "dataset_version": str(audit.dataset_version),
        "source_canonical_content_sha256": source_canonical_content_sha256,
        "identity_snapshot_version": identity_snapshot_version,
        "calendar_definition_version": audit.calendar_definition_version,
        "calendar_evidence_refs": list(policy.evidence_refs),
        "dataset_end_date": audit.dataset_end_date.isoformat(),
        "instrument_count": audit.instrument_count,
        "complete_instrument_count": audit.complete_instrument_count,
        "missing_history_instrument_count": audit.missing_history_instrument_count,
        "expected_session_observation_count": audit.expected_session_observation_count,
        "missing_expected_session_count": audit.missing_expected_session_count,
        "unexpected_observed_date_count": audit.unexpected_observed_date_count,
        "duplicate_observed_date_count": audit.duplicate_observed_date_count,
        "complete": audit.complete,
        "instruments": [_instrument_payload(item) for item in audit.instruments],
        "provider_calls_made": False,
        "bars_fabricated": 0,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _audit_instrument(
    *,
    instrument: InstrumentRecord,
    bars: tuple[DailyBar, ...],
    dataset_end_date: date,
    calendar: ExchangeSessionCalendar,
) -> InstrumentSessionCompleteness:
    expected_end = (
        min(dataset_end_date, instrument.delisting_date)
        if instrument.delisting_date is not None
        else dataset_end_date
    )
    if not bars:
        no_history_required = (
            instrument.first_trade_date is not None and instrument.first_trade_date > expected_end
        )
        return InstrumentSessionCompleteness(
            instrument_id=instrument.instrument_id,
            exchange=instrument.exchange,
            expected_start_date=instrument.first_trade_date,
            expected_end_date=expected_end,
            observed_first_date=None,
            observed_last_date=None,
            observed_bar_count=0,
            distinct_observed_date_count=0,
            expected_session_count=0,
            duplicate_observed_date_count=0,
            missing_history=not no_history_required,
            missing_expected_sessions=(),
            unexpected_observed_dates=(),
        )

    observed_dates = tuple(bar.trade_date for bar in bars)
    distinct_dates = frozenset(observed_dates)
    observed_first = min(distinct_dates)
    observed_last = max(distinct_dates)
    expected_start = instrument.first_trade_date or observed_first
    expected = frozenset(
        expected_exchange_sessions(
            exchange=instrument.exchange,
            start=expected_start,
            end=expected_end,
            calendar=calendar,
        )
    )
    return InstrumentSessionCompleteness(
        instrument_id=instrument.instrument_id,
        exchange=instrument.exchange,
        expected_start_date=expected_start,
        expected_end_date=expected_end,
        observed_first_date=observed_first,
        observed_last_date=observed_last,
        observed_bar_count=len(observed_dates),
        distinct_observed_date_count=len(distinct_dates),
        expected_session_count=len(expected),
        duplicate_observed_date_count=len(observed_dates) - len(distinct_dates),
        missing_history=False,
        missing_expected_sessions=tuple(sorted(expected - distinct_dates)),
        unexpected_observed_dates=tuple(sorted(distinct_dates - expected)),
    )


def _is_expected_session(day: date, calendar: ExchangeSessionCalendar) -> bool:
    return (
        day.weekday() < 5
        and day not in calendar.exceptional_closures
        and not _is_regular_full_day_holiday(day)
    )


def _is_regular_full_day_holiday(day: date) -> bool:
    year = day.year
    if day == date(year, 1, 1):
        return True
    if date(year, 1, 1).weekday() == 6 and day == date(year, 1, 2):
        return True
    if day == _nth_weekday(year, 1, 0, 3):
        return True
    if day == _nth_weekday(year, 2, 0, 3):
        return True
    if day == _easter_sunday(year) - timedelta(days=2):
        return True
    if day == _last_weekday(year, 5, 0):
        return True
    if year >= 2022 and day == _observed_fixed_holiday(year, 6, 19):
        return True
    if day == _observed_fixed_holiday(year, 7, 4):
        return True
    if day == _nth_weekday(year, 9, 0, 1):
        return True
    if day == _nth_weekday(year, 11, 3, 4):
        return True
    return day == _observed_fixed_holiday(year, 12, 25)


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, ordinal: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (ordinal - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    """Gregorian Easter using the Meeus/Jones/Butcher computus."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _closure(day: date, label: str, evidence_ref: str) -> ExceptionalClosure:
    return ExceptionalClosure(day, label, (evidence_ref,))


def _instrument_payload(item: InstrumentSessionCompleteness) -> dict[str, object]:
    return {
        "instrument_id": str(item.instrument_id),
        "exchange": item.exchange,
        "expected_start_date": _date_text(item.expected_start_date),
        "expected_end_date": item.expected_end_date.isoformat(),
        "observed_first_date": _date_text(item.observed_first_date),
        "observed_last_date": _date_text(item.observed_last_date),
        "observed_bar_count": item.observed_bar_count,
        "distinct_observed_date_count": item.distinct_observed_date_count,
        "expected_session_count": item.expected_session_count,
        "duplicate_observed_date_count": item.duplicate_observed_date_count,
        "missing_history": item.missing_history,
        "missing_expected_sessions": [day.isoformat() for day in item.missing_expected_sessions],
        "unexpected_observed_dates": [day.isoformat() for day in item.unexpected_observed_dates],
        "complete": item.complete,
    }


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "US_EQUITY_SESSION_CALENDAR_VERSION",
    "DatasetSessionCompletenessAudit",
    "ExceptionalClosure",
    "ExchangeSessionCalendar",
    "InstrumentSessionCompleteness",
    "SessionCompletenessError",
    "audit_daily_bar_session_completeness",
    "default_us_equity_session_calendar",
    "expected_exchange_sessions",
    "persist_session_completeness_report",
]
