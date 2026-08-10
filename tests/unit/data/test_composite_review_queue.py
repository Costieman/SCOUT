from datetime import date

import pytest

from trade_scout.data.composite_adjudication import CompositeAdjudicationState
from trade_scout.data.composite_evidence import (
    CompositeCoverageState,
    CompositeEvidenceReport,
    CompositeEvidenceRow,
    CompositeEvidenceSummary,
)
from trade_scout.data.composite_review_queue import (
    CompositeReviewKind,
    CompositeReviewQueueError,
    CompositeReviewResolution,
    adjudicate_composite_report,
    build_composite_review_queue,
)
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.provider import ProviderDailyBar


def _bar(provider_id: str, provider_instrument_id: str, symbol: str) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id=provider_id,
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        trade_date=date(2026, 1, 2),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
    )


def _row(
    state: CompositeCoverageState,
    *,
    alpha: ProviderDailyBar | None,
    stooq: ProviderDailyBar | None,
    differing_fields: tuple[str, ...] = (),
) -> CompositeEvidenceRow:
    return CompositeEvidenceRow(
        instrument_id=InstrumentId("instrument:spy"),
        trade_date=date(2026, 1, 2),
        provider_a_id="alpha_vantage",
        provider_b_id="stooq",
        state=state,
        provider_a_bar=alpha,
        provider_b_bar=stooq,
        differing_fields=differing_fields,
    )


def _report(row: CompositeEvidenceRow) -> CompositeEvidenceReport:
    counts = {
        CompositeCoverageState.BOTH_AGREE: (1, 0, 0, 0),
        CompositeCoverageState.BOTH_DISAGREE: (0, 1, 0, 0),
        CompositeCoverageState.A_ONLY: (0, 0, 1, 0),
        CompositeCoverageState.B_ONLY: (0, 0, 0, 1),
    }[row.state]
    return CompositeEvidenceReport(
        rows=(row,),
        summary=CompositeEvidenceSummary(
            row_count=1,
            both_agree_count=counts[0],
            both_disagree_count=counts[1],
            a_only_count=counts[2],
            b_only_count=counts[3],
        ),
    )


def test_corroborated_row_creates_no_review_work() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    queue = build_composite_review_queue(
        _report(_row(CompositeCoverageState.BOTH_AGREE, alpha=alpha, stooq=stooq))
    )
    assert queue == ()


def test_gap_row_creates_deterministic_review_item() -> None:
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    report = _report(_row(CompositeCoverageState.B_ONLY, alpha=None, stooq=stooq))
    first = build_composite_review_queue(report)
    second = build_composite_review_queue(report)

    assert first == second
    assert first[0].kind is CompositeReviewKind.GAP
    assert first[0].provider_a_present is False
    assert first[0].provider_b_present is True


def test_discrepancy_queue_retains_differing_fields() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    queue = build_composite_review_queue(
        _report(
            _row(
                CompositeCoverageState.BOTH_DISAGREE,
                alpha=alpha,
                stooq=stooq,
                differing_fields=("close_raw", "volume_raw"),
            )
        )
    )
    assert queue[0].kind is CompositeReviewKind.DISCREPANCY
    assert queue[0].differing_fields == ("close_raw", "volume_raw")


def test_complete_resolution_produces_final_decision() -> None:
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    report = _report(_row(CompositeCoverageState.B_ONLY, alpha=None, stooq=stooq))
    item = build_composite_review_queue(report)[0]
    decisions = adjudicate_composite_report(
        report,
        (
            CompositeReviewResolution(
                review_id=item.review_id,
                final_state=CompositeAdjudicationState.SECONDARY_ACCEPTED,
                review_note="Expected session and identity independently confirmed.",
            ),
        ),
    )
    assert decisions[0].state is CompositeAdjudicationState.SECONDARY_ACCEPTED
    assert decisions[0].selected_provider_id == "stooq"


def test_incomplete_review_batch_fails_closed() -> None:
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    report = _report(_row(CompositeCoverageState.B_ONLY, alpha=None, stooq=stooq))
    with pytest.raises(CompositeReviewQueueError, match="coverage mismatch"):
        adjudicate_composite_report(report, ())
