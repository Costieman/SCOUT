"""Provider-neutral evidence checks for reproducible historical OHLCV retrieval.

This module evaluates bounded historical retrieval behavior through the stable ProviderAdapter
boundary. It produces evidence only; it does not accept a provider, repair data, infer a trading
calendar, or promote retrieved observations into canonical storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest, ProviderAdapter, ProviderDailyBar


class HistoricalEvidenceState(StrEnum):
    """Outcome of one historical-retrieval evidence check."""

    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceCase:
    """Explicit bounded sample used to characterize historical OHLCV retrieval."""

    case_id: str
    provider_symbol: str
    start: date
    end: date
    minimum_observations: int
    max_start_lag_days: int = 10
    max_end_lag_days: int = 10

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("historical evidence case_id must be non-empty")
        if not self.provider_symbol.strip():
            raise ValueError("historical evidence provider_symbol must be non-empty")
        if self.end < self.start:
            raise ValueError("historical evidence end must be on or after start")
        if self.minimum_observations < 1:
            raise ValueError("minimum_observations must be positive")
        if self.max_start_lag_days < 0 or self.max_end_lag_days < 0:
            raise ValueError("coverage lag tolerances must be non-negative")


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceCheck:
    """One auditable assertion about a historical retrieval sample."""

    check_id: str
    state: HistoricalEvidenceState
    detail: str


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceCaseResult:
    """Evidence collected for one bounded historical sample."""

    case_id: str
    provider_symbol: str
    observation_count: int
    first_trade_date: date | None
    last_trade_date: date | None
    checks: tuple[HistoricalEvidenceCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.state is HistoricalEvidenceState.PASS for check in self.checks)


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceReport:
    """Provider-level historical OHLCV evidence without an acceptance decision."""

    provider_id: str
    cases: tuple[HistoricalEvidenceCaseResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)


def evaluate_historical_ohlcv(
    adapter: ProviderAdapter,
    cases: tuple[HistoricalEvidenceCase, ...],
) -> HistoricalEvidenceReport:
    """Evaluate reproducibility, scope, identity, uniqueness, and date coverage.

    Each case is retrieved twice through the same provider-neutral request. Exact normalized-record
    equality is required between the two retrievals. Date-coverage tolerances are calendar-day
    tolerances supplied by the caller; this function deliberately does not invent a trading calendar.
    """

    if not cases:
        raise ValueError("historical OHLCV evidence requires at least one case")
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("historical evidence case_id values must be unique")

    results = tuple(_evaluate_case(adapter, case) for case in cases)
    return HistoricalEvidenceReport(provider_id=adapter.provider_id, cases=results)


def _evaluate_case(
    adapter: ProviderAdapter,
    case: HistoricalEvidenceCase,
) -> HistoricalEvidenceCaseResult:
    request = DailyBarRequest(
        start=case.start,
        end=case.end,
        provider_symbols=(case.provider_symbol,),
        adjustment=PriceRepresentation.RAW,
        run_id=f"historical-evidence:{case.case_id}",
    )
    first = tuple(adapter.get_daily_bars(request))
    second = tuple(adapter.get_daily_bars(request))

    checks = [
        HistoricalEvidenceCheck(
            check_id="repeatability",
            state=_state(first == second),
            detail=f"first_count={len(first)}, second_count={len(second)}",
        )
    ]
    checks.extend(_scope_checks(adapter.provider_id, case, first))

    dates = tuple(bar.trade_date for bar in first)
    first_date = min(dates) if dates else None
    last_date = max(dates) if dates else None
    checks.append(
        HistoricalEvidenceCheck(
            check_id="minimum_observations",
            state=_state(len(first) >= case.minimum_observations),
            detail=f"observed={len(first)}, required={case.minimum_observations}",
        )
    )
    checks.append(
        HistoricalEvidenceCheck(
            check_id="start_coverage",
            state=_state(
                first_date is not None
                and (first_date - case.start).days <= case.max_start_lag_days
            ),
            detail=(
                f"requested_start={case.start.isoformat()}, first_trade_date="
                f"{first_date.isoformat() if first_date else 'NONE'}, "
                f"max_lag_days={case.max_start_lag_days}"
            ),
        )
    )
    checks.append(
        HistoricalEvidenceCheck(
            check_id="end_coverage",
            state=_state(
                last_date is not None and (case.end - last_date).days <= case.max_end_lag_days
            ),
            detail=(
                f"requested_end={case.end.isoformat()}, last_trade_date="
                f"{last_date.isoformat() if last_date else 'NONE'}, "
                f"max_lag_days={case.max_end_lag_days}"
            ),
        )
    )

    return HistoricalEvidenceCaseResult(
        case_id=case.case_id,
        provider_symbol=case.provider_symbol,
        observation_count=len(first),
        first_trade_date=first_date,
        last_trade_date=last_date,
        checks=tuple(checks),
    )


def _scope_checks(
    provider_id: str,
    case: HistoricalEvidenceCase,
    bars: tuple[ProviderDailyBar, ...],
) -> tuple[HistoricalEvidenceCheck, ...]:
    wrong_provider = tuple(bar for bar in bars if bar.provider_id != provider_id)
    wrong_symbol = tuple(bar for bar in bars if bar.symbol != case.provider_symbol)
    out_of_range = tuple(bar for bar in bars if not case.start <= bar.trade_date <= case.end)

    keys = [(bar.provider_instrument_id, bar.trade_date) for bar in bars]
    duplicate_count = len(keys) - len(set(keys))
    ordered = tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.trade_date)))

    return (
        HistoricalEvidenceCheck(
            check_id="provider_scope",
            state=_state(not wrong_provider),
            detail=f"wrong_provider_count={len(wrong_provider)}",
        ),
        HistoricalEvidenceCheck(
            check_id="symbol_scope",
            state=_state(not wrong_symbol),
            detail=f"wrong_symbol_count={len(wrong_symbol)}",
        ),
        HistoricalEvidenceCheck(
            check_id="date_scope",
            state=_state(not out_of_range),
            detail=f"out_of_range_count={len(out_of_range)}",
        ),
        HistoricalEvidenceCheck(
            check_id="unique_instrument_session",
            state=_state(duplicate_count == 0),
            detail=f"duplicate_count={duplicate_count}",
        ),
        HistoricalEvidenceCheck(
            check_id="deterministic_order",
            state=_state(bars == ordered),
            detail="records must be ordered by symbol and trade_date",
        ),
    )


def _state(condition: bool) -> HistoricalEvidenceState:
    return HistoricalEvidenceState.PASS if condition else HistoricalEvidenceState.FAIL
