"""Aggregate cross-provider reconciliation results into auditable Phase 1 evidence."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from trade_scout.data.reconciliation import ReconciliationResult, ReconciliationState


@dataclass(frozen=True, slots=True)
class ReconciliationEvidenceSummary:
    """Aggregate comparison coverage and unresolved discrepancy burden."""

    comparison_count: int
    state_counts: dict[ReconciliationState, int]
    comparable_count: int
    agreement_count: int
    unresolved_count: int
    not_comparable_count: int

    @property
    def comparable_fraction(self) -> float:
        return self.comparable_count / self.comparison_count if self.comparison_count else 0.0

    @property
    def agreement_fraction_of_comparable(self) -> float:
        return self.agreement_count / self.comparable_count if self.comparable_count else 0.0

    @property
    def has_unresolved_discrepancies(self) -> bool:
        return self.unresolved_count > 0


def summarize_reconciliation_evidence(
    results: tuple[ReconciliationResult, ...],
) -> ReconciliationEvidenceSummary:
    """Summarize results without converting unresolved discrepancies into acceptance decisions."""

    counts = Counter(result.state for result in results)
    not_comparable = counts[ReconciliationState.NOT_COMPARABLE]
    comparable = len(results) - not_comparable
    agreement = counts[ReconciliationState.AGREE]
    unresolved = counts[ReconciliationState.UNRESOLVED]
    return ReconciliationEvidenceSummary(
        comparison_count=len(results),
        state_counts={state: counts[state] for state in ReconciliationState},
        comparable_count=comparable,
        agreement_count=agreement,
        unresolved_count=unresolved,
        not_comparable_count=not_comparable,
    )
