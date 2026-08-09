from __future__ import annotations

from trade_scout.data.contracts import InstrumentId
from trade_scout.data.reconciliation import ReconciliationResult, ReconciliationState
from trade_scout.data.reconciliation_evidence import summarize_reconciliation_evidence


def _result(state: ReconciliationState) -> ReconciliationResult:
    return ReconciliationResult(
        instrument_id=InstrumentId("tsi_fixture"),
        trade_date="2020-01-02",
        primary_provider_id="primary",
        secondary_provider_id="secondary"
        if state is not ReconciliationState.NOT_COMPARABLE
        else None,
        state=state,
        differences=(),
    )


def test_summary_preserves_unresolved_and_not_comparable_states() -> None:
    summary = summarize_reconciliation_evidence(
        (
            _result(ReconciliationState.AGREE),
            _result(ReconciliationState.AGREE),
            _result(ReconciliationState.UNRESOLVED),
            _result(ReconciliationState.NOT_COMPARABLE),
        )
    )

    assert summary.comparison_count == 4
    assert summary.comparable_count == 3
    assert summary.agreement_count == 2
    assert summary.unresolved_count == 1
    assert summary.not_comparable_count == 1
    assert summary.comparable_fraction == 0.75
    assert summary.agreement_fraction_of_comparable == 2 / 3
    assert summary.has_unresolved_discrepancies is True


def test_empty_summary_does_not_imply_success() -> None:
    summary = summarize_reconciliation_evidence(())

    assert summary.comparison_count == 0
    assert summary.comparable_fraction == 0.0
    assert summary.agreement_fraction_of_comparable == 0.0
