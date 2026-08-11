from datetime import date

from trade_scout.data.composite_evidence import (
    CompositeCoverageState,
    CompositeEvidenceReport,
    CompositeEvidenceRow,
    CompositeEvidenceSummary,
)
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.historical_edge import HistoricalEdgeStatus, classify_initial_history_gap


INSTRUMENT_ID = InstrumentId("historical-edge-test")
GAP_DATES = (date(2001, 1, 26), date(2001, 1, 29))
ANCHOR_DATE = date(2001, 1, 30)


def test_secondary_confirms_reviewed_primary_gap() -> None:
    evidence = _report(
        (date(2001, 1, 26), CompositeCoverageState.B_ONLY),
        (date(2001, 1, 29), CompositeCoverageState.B_ONLY),
        (date(2001, 1, 30), CompositeCoverageState.BOTH_AGREE),
    )

    assert (
        classify_initial_history_gap(
            evidence,
            expected_gap_sessions=GAP_DATES,
            anchor_date=ANCHOR_DATE,
        )
        is HistoricalEdgeStatus.SECONDARY_CONFIRMS_PRIMARY_GAP
    )


def test_primary_coverage_change_takes_precedence() -> None:
    evidence = _report(
        (date(2001, 1, 26), CompositeCoverageState.BOTH_AGREE),
        (date(2001, 1, 29), CompositeCoverageState.B_ONLY),
        (date(2001, 1, 30), CompositeCoverageState.BOTH_AGREE),
    )

    assert (
        classify_initial_history_gap(
            evidence,
            expected_gap_sessions=GAP_DATES,
            anchor_date=ANCHOR_DATE,
        )
        is HistoricalEdgeStatus.PRIMARY_COVERAGE_CHANGED
    )


def test_secondary_nonobservation_remains_inconclusive() -> None:
    evidence = _report(
        (date(2001, 1, 26), CompositeCoverageState.B_ONLY),
        (date(2001, 1, 30), CompositeCoverageState.BOTH_AGREE),
    )

    assert (
        classify_initial_history_gap(
            evidence,
            expected_gap_sessions=GAP_DATES,
            anchor_date=ANCHOR_DATE,
        )
        is HistoricalEdgeStatus.INCONCLUSIVE_SECONDARY_NONOBSERVATION
    )


def test_anchor_disagreement_blocks_confirmation() -> None:
    evidence = _report(
        (date(2001, 1, 26), CompositeCoverageState.B_ONLY),
        (date(2001, 1, 29), CompositeCoverageState.B_ONLY),
        (date(2001, 1, 30), CompositeCoverageState.BOTH_DISAGREE),
    )

    assert (
        classify_initial_history_gap(
            evidence,
            expected_gap_sessions=GAP_DATES,
            anchor_date=ANCHOR_DATE,
        )
        is HistoricalEdgeStatus.ANCHOR_DISAGREEMENT
    )


def _report(*states: tuple[date, CompositeCoverageState]) -> CompositeEvidenceReport:
    rows = tuple(
        CompositeEvidenceRow(
            instrument_id=INSTRUMENT_ID,
            trade_date=trade_date,
            provider_a_id="tiingo",
            provider_b_id="alpha_vantage",
            state=state,
            provider_a_bar=None,
            provider_b_bar=None,
            differing_fields=("close_raw",)
            if state is CompositeCoverageState.BOTH_DISAGREE
            else (),
        )
        for trade_date, state in states
    )
    summary = CompositeEvidenceSummary(
        row_count=len(rows),
        both_agree_count=sum(row.state is CompositeCoverageState.BOTH_AGREE for row in rows),
        both_disagree_count=sum(row.state is CompositeCoverageState.BOTH_DISAGREE for row in rows),
        a_only_count=sum(row.state is CompositeCoverageState.A_ONLY for row in rows),
        b_only_count=sum(row.state is CompositeCoverageState.B_ONLY for row in rows),
    )
    return CompositeEvidenceReport(rows=rows, summary=summary)
