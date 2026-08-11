from datetime import date

import pytest

from trade_scout.data.composite_evidence import (
    CompositeCoverageState,
    CompositeEvidenceReport,
    CompositeEvidenceRow,
    CompositeEvidenceSummary,
)
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.provider_complementarity import (
    summarize_provider_complementarity,
)

INSTRUMENT_ID = InstrumentId("reviewed-instrument-001")


def test_summarizes_expected_session_complementarity() -> None:
    evidence = _report(
        (date(2026, 8, 3), CompositeCoverageState.BOTH_AGREE),
        (date(2026, 8, 4), CompositeCoverageState.BOTH_DISAGREE),
        (date(2026, 8, 5), CompositeCoverageState.A_ONLY),
        (date(2026, 8, 6), CompositeCoverageState.B_ONLY),
    )

    summary = summarize_provider_complementarity(
        evidence,
        expected_sessions=(
            date(2026, 8, 3),
            date(2026, 8, 4),
            date(2026, 8, 5),
            date(2026, 8, 6),
            date(2026, 8, 7),
        ),
    )

    assert summary.expected_session_count == 5
    assert summary.provider_a_session_count == 3
    assert summary.provider_b_session_count == 3
    assert summary.union_session_count == 4
    assert summary.both_agree_count == 1
    assert summary.both_disagree_count == 1
    assert summary.provider_a_only_count == 1
    assert summary.provider_b_only_count == 1
    assert summary.both_missing_count == 1
    assert summary.complementary_session_count == 2
    assert summary.provider_a_coverage_fraction == pytest.approx(0.6)
    assert summary.provider_b_coverage_fraction == pytest.approx(0.6)
    assert summary.union_coverage_fraction == pytest.approx(0.8)
    assert summary.union_gain_over_a_fraction == pytest.approx(0.2)
    assert summary.union_gain_over_b_fraction == pytest.approx(0.2)


def test_rejects_evidence_outside_expected_sessions() -> None:
    evidence = _report((date(2026, 8, 4), CompositeCoverageState.A_ONLY))

    with pytest.raises(ValueError, match="unexpected sessions"):
        summarize_provider_complementarity(
            evidence,
            expected_sessions=(date(2026, 8, 3),),
        )


def test_rejects_duplicate_expected_sessions() -> None:
    evidence = _report()

    with pytest.raises(ValueError, match="duplicate dates"):
        summarize_provider_complementarity(
            evidence,
            expected_sessions=(date(2026, 8, 3), date(2026, 8, 3)),
        )


def _report(
    *states: tuple[date, CompositeCoverageState],
) -> CompositeEvidenceReport:
    rows = tuple(
        CompositeEvidenceRow(
            instrument_id=INSTRUMENT_ID,
            trade_date=trade_date,
            provider_a_id="provider_a",
            provider_b_id="provider_b",
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
