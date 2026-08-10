"""Targeted independent-provider evidence for known canonical coverage gaps.

This module does not fill, interpolate, or promote bars. It only derives the exact expected
exchange sessions between a reviewed lifecycle start and a provider's observed coverage start,
then classifies whether an independent validator observed those sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.session_completeness import (
    US_EQUITY_SESSION_CALENDAR_VERSION,
    expected_exchange_sessions,
)


class TargetedGapValidationError(RuntimeError):
    """Raised when targeted gap evidence is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class TargetedGapCase:
    """One reviewed lifecycle/provider-coverage discrepancy requiring independent evidence."""

    case_id: str
    symbol: str
    exchange: str
    lifecycle_start_date: date
    observed_provider_id: str
    observed_first_date: date
    validator_provider_id: str
    validator_symbol: str
    anchor_date: date
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must be non-empty")
        if not self.symbol.strip() or not self.validator_symbol.strip():
            raise ValueError("symbols must be non-empty")
        if not self.observed_provider_id.strip() or not self.validator_provider_id.strip():
            raise ValueError("provider IDs must be non-empty")
        if self.observed_first_date <= self.lifecycle_start_date:
            raise ValueError("observed_first_date must be after lifecycle_start_date")
        if self.anchor_date < self.observed_first_date:
            raise ValueError("anchor_date must be on or after observed_first_date")
        if not self.evidence_refs:
            raise ValueError("targeted gap case requires lifecycle evidence")


@dataclass(frozen=True, slots=True)
class TargetedGapValidationResult:
    """Metadata-only result of an independent-provider gap check."""

    case: TargetedGapCase
    calendar_definition_version: str
    expected_gap_sessions: tuple[date, ...]
    validator_present_gap_sessions: tuple[date, ...]
    validator_missing_gap_sessions: tuple[date, ...]
    validator_anchor_present: bool
    validator_observed_session_count: int

    @property
    def gap_fully_observed_by_validator(self) -> bool:
        return bool(self.expected_gap_sessions) and not self.validator_missing_gap_sessions

    @property
    def ready_for_manual_adjudication(self) -> bool:
        """Require all target sessions plus an overlap anchor; never imply automatic fill."""

        return self.gap_fully_observed_by_validator and self.validator_anchor_present


def expected_target_gap_sessions(case: TargetedGapCase) -> tuple[date, ...]:
    """Derive missing expected sessions without trusting a manually typed date list."""

    return expected_exchange_sessions(
        exchange=case.exchange,
        start=case.lifecycle_start_date,
        end=case.observed_first_date - timedelta(days=1),
    )


def evaluate_targeted_gap_validator(
    case: TargetedGapCase,
    bars: tuple[ProviderDailyBar, ...],
) -> TargetedGapValidationResult:
    """Classify validator date coverage for the exact expected gap and overlap anchor."""

    expected = expected_target_gap_sessions(case)
    if not expected:
        raise TargetedGapValidationError("targeted gap case contains no expected missing sessions")

    observed_dates: set[date] = set()
    for bar in bars:
        if bar.provider_id != case.validator_provider_id:
            raise TargetedGapValidationError(
                f"validator bar provider mismatch: {bar.provider_id} != {case.validator_provider_id}"
            )
        if bar.symbol.upper() != case.validator_symbol.upper():
            raise TargetedGapValidationError(
                f"validator bar symbol mismatch: {bar.symbol} != {case.validator_symbol}"
            )
        if bar.trade_date in observed_dates:
            raise TargetedGapValidationError(
                f"duplicate validator session for {case.validator_symbol} {bar.trade_date}"
            )
        observed_dates.add(bar.trade_date)

    present = tuple(day for day in expected if day in observed_dates)
    missing = tuple(day for day in expected if day not in observed_dates)
    return TargetedGapValidationResult(
        case=case,
        calendar_definition_version=US_EQUITY_SESSION_CALENDAR_VERSION,
        expected_gap_sessions=expected,
        validator_present_gap_sessions=present,
        validator_missing_gap_sessions=missing,
        validator_anchor_present=case.anchor_date in observed_dates,
        validator_observed_session_count=len(observed_dates),
    )


__all__ = [
    "TargetedGapCase",
    "TargetedGapValidationError",
    "TargetedGapValidationResult",
    "evaluate_targeted_gap_validator",
    "expected_target_gap_sessions",
]
