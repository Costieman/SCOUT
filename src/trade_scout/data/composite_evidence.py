"""Provider-neutral A+B coverage classification for the free-data research foundation.

This module does not construct canonical bars. It classifies what two raw providers
contribute for each reviewed instrument/session so downstream promotion remains an
explicit, auditable decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import InstrumentId
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.raw_reconciliation import compare_raw_validation_bars
from trade_scout.data.reconciliation import ReconciliationTolerance, raw_validation_bar


class CompositeCoverageState(StrEnum):
    """Observed A+B contribution state for one instrument/session."""

    BOTH_AGREE = "BOTH_AGREE"
    BOTH_DISAGREE = "BOTH_DISAGREE"
    A_ONLY = "A_ONLY"
    B_ONLY = "B_ONLY"


@dataclass(frozen=True, slots=True)
class CompositeEvidenceRow:
    instrument_id: InstrumentId
    trade_date: date
    provider_a_id: str
    provider_b_id: str
    state: CompositeCoverageState
    provider_a_bar: ProviderDailyBar | None
    provider_b_bar: ProviderDailyBar | None
    differing_fields: tuple[str, ...] = ()

    @property
    def canonicalizable_without_review(self) -> bool:
        """Only corroborated A+B agreement is safe to promote automatically."""

        return self.state is CompositeCoverageState.BOTH_AGREE

    @property
    def requires_gap_review(self) -> bool:
        return self.state in {CompositeCoverageState.A_ONLY, CompositeCoverageState.B_ONLY}

    @property
    def requires_discrepancy_review(self) -> bool:
        return self.state is CompositeCoverageState.BOTH_DISAGREE


@dataclass(frozen=True, slots=True)
class CompositeEvidenceSummary:
    row_count: int
    both_agree_count: int
    both_disagree_count: int
    a_only_count: int
    b_only_count: int

    @property
    def corroborated_fraction(self) -> float | None:
        if self.row_count == 0:
            return None
        return self.both_agree_count / self.row_count

    @property
    def one_sided_fraction(self) -> float | None:
        if self.row_count == 0:
            return None
        return (self.a_only_count + self.b_only_count) / self.row_count


@dataclass(frozen=True, slots=True)
class CompositeEvidenceReport:
    rows: tuple[CompositeEvidenceRow, ...]
    summary: CompositeEvidenceSummary


def build_composite_evidence(
    *,
    instrument_id: InstrumentId,
    provider_a_id: str,
    provider_a_instrument_id: str,
    provider_a_bars: tuple[ProviderDailyBar, ...],
    provider_b_id: str,
    provider_b_instrument_id: str,
    provider_b_bars: tuple[ProviderDailyBar, ...],
    tolerance: ReconciliationTolerance,
) -> CompositeEvidenceReport:
    """Classify the union of A+B sessions without filling, averaging, or voting."""

    a = _index(
        provider_a_bars,
        provider_id=provider_a_id,
        provider_instrument_id=provider_a_instrument_id,
    )
    b = _index(
        provider_b_bars,
        provider_id=provider_b_id,
        provider_instrument_id=provider_b_instrument_id,
    )
    rows: list[CompositeEvidenceRow] = []
    for trade_date in sorted(set(a) | set(b)):
        bar_a = a.get(trade_date)
        bar_b = b.get(trade_date)
        if bar_a is None:
            state = CompositeCoverageState.B_ONLY
            differing_fields: tuple[str, ...] = ()
        elif bar_b is None:
            state = CompositeCoverageState.A_ONLY
            differing_fields = ()
        else:
            raw_a = raw_validation_bar(
                bar_a,
                instrument_id=instrument_id,
                expected_provider_instrument_id=provider_a_instrument_id,
            )
            raw_b = raw_validation_bar(
                bar_b,
                instrument_id=instrument_id,
                expected_provider_instrument_id=provider_b_instrument_id,
            )
            comparison = compare_raw_validation_bars(raw_a, raw_b, tolerance=tolerance)
            if comparison.differences:
                state = CompositeCoverageState.BOTH_DISAGREE
                differing_fields = tuple(item.field for item in comparison.differences)
            else:
                state = CompositeCoverageState.BOTH_AGREE
                differing_fields = ()
        rows.append(
            CompositeEvidenceRow(
                instrument_id=instrument_id,
                trade_date=trade_date,
                provider_a_id=provider_a_id,
                provider_b_id=provider_b_id,
                state=state,
                provider_a_bar=bar_a,
                provider_b_bar=bar_b,
                differing_fields=differing_fields,
            )
        )
    frozen = tuple(rows)
    return CompositeEvidenceReport(rows=frozen, summary=_summarize(frozen))


def _index(
    bars: tuple[ProviderDailyBar, ...],
    *,
    provider_id: str,
    provider_instrument_id: str,
) -> dict[date, ProviderDailyBar]:
    indexed: dict[date, ProviderDailyBar] = {}
    for bar in bars:
        if bar.provider_id != provider_id:
            raise ValueError("composite evidence contains the wrong provider")
        if bar.provider_instrument_id != provider_instrument_id:
            raise ValueError("composite evidence contains the wrong provider identity")
        if bar.trade_date in indexed:
            raise ValueError("composite evidence contains duplicate provider sessions")
        indexed[bar.trade_date] = bar
    return indexed


def _summarize(rows: tuple[CompositeEvidenceRow, ...]) -> CompositeEvidenceSummary:
    return CompositeEvidenceSummary(
        row_count=len(rows),
        both_agree_count=sum(row.state is CompositeCoverageState.BOTH_AGREE for row in rows),
        both_disagree_count=sum(row.state is CompositeCoverageState.BOTH_DISAGREE for row in rows),
        a_only_count=sum(row.state is CompositeCoverageState.A_ONLY for row in rows),
        b_only_count=sum(row.state is CompositeCoverageState.B_ONLY for row in rows),
    )
