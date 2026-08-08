"""Context-aware completeness, cross-sectional, and corporate-action quality checks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from trade_scout.data.contracts import (
    CorporateActionRecord,
    DailyBar,
    InstrumentId,
    QualityStatus,
)


@dataclass(frozen=True, slots=True)
class CoveragePolicy:
    """Explicit thresholds used to classify missing expected market observations."""

    warn_missing_fraction: float
    quarantine_missing_fraction: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.warn_missing_fraction <= 1.0:
            raise ValueError("warn_missing_fraction must lie in [0, 1]")
        if not 0.0 <= self.quarantine_missing_fraction <= 1.0:
            raise ValueError("quarantine_missing_fraction must lie in [0, 1]")
        if self.quarantine_missing_fraction < self.warn_missing_fraction:
            raise ValueError("quarantine threshold cannot be below warn threshold")


@dataclass(frozen=True, slots=True)
class MissingObservation:
    """Expected instrument/session pair absent from the supplied canonical bars."""

    instrument_id: InstrumentId
    trade_date: date


@dataclass(frozen=True, slots=True)
class UnexpectedObservation:
    """Observed instrument/session pair outside the supplied point-in-time expectation."""

    instrument_id: InstrumentId
    trade_date: date


@dataclass(frozen=True, slots=True)
class CompletenessReport:
    """Coverage result against caller-supplied point-in-time session membership."""

    status: QualityStatus
    expected_count: int
    observed_expected_count: int
    missing_count: int
    missing_fraction: float
    missing: tuple[MissingObservation, ...]
    unexpected: tuple[UnexpectedObservation, ...]


@dataclass(frozen=True, slots=True)
class CrossSectionExpectation:
    """Permitted active-instrument count range for one historical session."""

    trade_date: date
    minimum_count: int
    maximum_count: int

    def __post_init__(self) -> None:
        if self.minimum_count < 0:
            raise ValueError("minimum_count must be non-negative")
        if self.maximum_count < self.minimum_count:
            raise ValueError("maximum_count must be at least minimum_count")


@dataclass(frozen=True, slots=True)
class CrossSectionCountResult:
    """Observed cross-sectional count compared with one explicit historical range."""

    trade_date: date
    observed_count: int
    minimum_count: int
    maximum_count: int
    status: QualityStatus


@dataclass(frozen=True, slots=True)
class CrossSectionReport:
    """Daily active-instrument count checks across supplied historical sessions."""

    status: QualityStatus
    sessions: tuple[CrossSectionCountResult, ...]


@dataclass(frozen=True, slots=True)
class PriceJumpPolicy:
    """Threshold and severity for unexplained raw close-to-close price jumps."""

    absolute_return_threshold: float
    unexplained_status: QualityStatus

    def __post_init__(self) -> None:
        if self.absolute_return_threshold <= 0:
            raise ValueError("absolute_return_threshold must be positive")
        if self.unexplained_status not in {
            QualityStatus.WARN,
            QualityStatus.QUARANTINE,
            QualityStatus.REJECT,
        }:
            raise ValueError("unexplained jump status must represent a detected issue")


@dataclass(frozen=True, slots=True)
class PriceJumpAnomaly:
    """Large raw close-to-close move with no supplied corporate-action explanation."""

    instrument_id: InstrumentId
    previous_trade_date: date
    trade_date: date
    previous_close_raw: float
    close_raw: float
    raw_return: float
    status: QualityStatus


@dataclass(frozen=True, slots=True)
class CorporateActionQualityReport:
    """Corporate-action consistency screen; observations are reported, never repaired."""

    status: QualityStatus
    anomalies: tuple[PriceJumpAnomaly, ...]


def validate_completeness(
    bars: Iterable[DailyBar],
    *,
    expected_instruments_by_session: Mapping[date, frozenset[InstrumentId]],
    policy: CoveragePolicy,
) -> CompletenessReport:
    """Compare bars with explicit point-in-time expectations without fabricating missing records."""

    expected_pairs = {
        (instrument_id, trade_date)
        for trade_date, instrument_ids in expected_instruments_by_session.items()
        for instrument_id in instrument_ids
    }
    observed_pairs = {(bar.instrument_id, bar.trade_date) for bar in bars}
    missing_pairs = expected_pairs - observed_pairs
    unexpected_pairs = observed_pairs - expected_pairs

    expected_count = len(expected_pairs)
    missing_count = len(missing_pairs)
    missing_fraction = missing_count / expected_count if expected_count else 0.0
    status = _coverage_status(missing_fraction, policy)

    return CompletenessReport(
        status=status,
        expected_count=expected_count,
        observed_expected_count=expected_count - missing_count,
        missing_count=missing_count,
        missing_fraction=missing_fraction,
        missing=tuple(
            MissingObservation(instrument_id=instrument_id, trade_date=trade_date)
            for instrument_id, trade_date in sorted(
                missing_pairs,
                key=lambda pair: (pair[1], str(pair[0])),
            )
        ),
        unexpected=tuple(
            UnexpectedObservation(instrument_id=instrument_id, trade_date=trade_date)
            for instrument_id, trade_date in sorted(
                unexpected_pairs,
                key=lambda pair: (pair[1], str(pair[0])),
            )
        ),
    )


def validate_cross_section_counts(
    bars: Iterable[DailyBar],
    *,
    expectations: Iterable[CrossSectionExpectation],
    out_of_range_status: QualityStatus,
) -> CrossSectionReport:
    """Check daily instrument counts against explicitly supplied historical ranges."""

    if out_of_range_status not in {
        QualityStatus.WARN,
        QualityStatus.QUARANTINE,
        QualityStatus.REJECT,
    }:
        raise ValueError("out_of_range_status must represent a detected issue")

    instruments_by_session: dict[date, set[InstrumentId]] = {}
    for bar in bars:
        instruments_by_session.setdefault(bar.trade_date, set()).add(bar.instrument_id)

    results: list[CrossSectionCountResult] = []
    for expectation in sorted(expectations, key=lambda item: item.trade_date):
        observed_count = len(instruments_by_session.get(expectation.trade_date, set()))
        within_range = expectation.minimum_count <= observed_count <= expectation.maximum_count
        results.append(
            CrossSectionCountResult(
                trade_date=expectation.trade_date,
                observed_count=observed_count,
                minimum_count=expectation.minimum_count,
                maximum_count=expectation.maximum_count,
                status=QualityStatus.PASS if within_range else out_of_range_status,
            )
        )

    frozen_results = tuple(results)
    return CrossSectionReport(
        status=_worst_status(result.status for result in frozen_results),
        sessions=frozen_results,
    )


def validate_corporate_action_price_jumps(
    bars: Iterable[DailyBar],
    *,
    corporate_actions: Iterable[CorporateActionRecord],
    policy: PriceJumpPolicy,
) -> CorporateActionQualityReport:
    """Flag large raw price jumps that lack a supplied corporate-action explanation."""

    actions_by_instrument: dict[InstrumentId, set[date]] = {}
    for action in corporate_actions:
        actions_by_instrument.setdefault(action.instrument_id, set()).add(action.effective_date)

    bars_by_instrument: dict[InstrumentId, list[DailyBar]] = {}
    for bar in bars:
        bars_by_instrument.setdefault(bar.instrument_id, []).append(bar)

    anomalies: list[PriceJumpAnomaly] = []
    for instrument_id, instrument_bars in bars_by_instrument.items():
        ordered = sorted(instrument_bars, key=lambda bar: bar.trade_date)
        action_dates = actions_by_instrument.get(instrument_id, set())
        for previous, current in pairwise(ordered):
            if previous.close_raw <= 0:
                continue
            raw_return = current.close_raw / previous.close_raw - 1.0
            if abs(raw_return) < policy.absolute_return_threshold:
                continue
            if _has_action_between(action_dates, previous.trade_date, current.trade_date):
                continue
            anomalies.append(
                PriceJumpAnomaly(
                    instrument_id=instrument_id,
                    previous_trade_date=previous.trade_date,
                    trade_date=current.trade_date,
                    previous_close_raw=previous.close_raw,
                    close_raw=current.close_raw,
                    raw_return=raw_return,
                    status=policy.unexplained_status,
                )
            )

    frozen_anomalies = tuple(
        sorted(anomalies, key=lambda item: (item.trade_date, str(item.instrument_id)))
    )
    return CorporateActionQualityReport(
        status=_worst_status(anomaly.status for anomaly in frozen_anomalies),
        anomalies=frozen_anomalies,
    )


def _coverage_status(missing_fraction: float, policy: CoveragePolicy) -> QualityStatus:
    if missing_fraction > policy.quarantine_missing_fraction:
        return QualityStatus.QUARANTINE
    if missing_fraction > policy.warn_missing_fraction:
        return QualityStatus.WARN
    return QualityStatus.PASS


def _has_action_between(action_dates: set[date], previous_date: date, current_date: date) -> bool:
    return any(previous_date < action_date <= current_date for action_date in action_dates)


def _worst_status(statuses: Iterable[QualityStatus]) -> QualityStatus:
    rank = {
        QualityStatus.PASS: 0,
        QualityStatus.WARN: 1,
        QualityStatus.QUARANTINE: 2,
        QualityStatus.REJECT: 3,
    }
    status = QualityStatus.PASS
    for candidate in statuses:
        if rank[candidate] > rank[status]:
            status = candidate
    return status
