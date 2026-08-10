from datetime import date

import pytest

from trade_scout.data.composite_adjudication import (
    CompositeAdjudicationState,
    InvalidCompositeAdjudicationError,
    propose_composite_adjudication,
    record_composite_review,
    selected_provider_bar,
)
from trade_scout.data.composite_evidence import CompositeCoverageState, CompositeEvidenceRow
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
        split_factor=None,
        dividend_cash=None,
    )


def _row(
    state: CompositeCoverageState,
    *,
    a: ProviderDailyBar | None,
    b: ProviderDailyBar | None,
) -> CompositeEvidenceRow:
    return CompositeEvidenceRow(
        instrument_id=InstrumentId("instrument:spy"),
        trade_date=date(2026, 1, 2),
        provider_a_id="alpha_vantage",
        provider_b_id="stooq",
        state=state,
        provider_a_bar=a,
        provider_b_bar=b,
    )


def test_agreement_is_corroborated_and_selects_primary() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    decision = propose_composite_adjudication(
        _row(CompositeCoverageState.BOTH_AGREE, a=alpha, b=stooq)
    )
    assert decision.state is CompositeAdjudicationState.CORROBORATED
    assert decision.is_promotable
    assert selected_provider_bar(decision) is alpha


def test_one_sided_observation_requires_review_before_selection() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    proposed = propose_composite_adjudication(
        _row(CompositeCoverageState.A_ONLY, a=alpha, b=None)
    )
    assert proposed.state is CompositeAdjudicationState.GAP_REVIEW_REQUIRED
    assert not proposed.is_promotable
    with pytest.raises(InvalidCompositeAdjudicationError):
        selected_provider_bar(proposed)

    reviewed = record_composite_review(
        proposed,
        state=CompositeAdjudicationState.PRIMARY_ACCEPTED,
        review_note="Expected session confirmed; secondary source is missing this observation.",
    )
    assert selected_provider_bar(reviewed) is alpha


def test_secondary_only_can_be_selected_only_by_explicit_review() -> None:
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    proposed = propose_composite_adjudication(
        _row(CompositeCoverageState.B_ONLY, a=None, b=stooq)
    )
    with pytest.raises(InvalidCompositeAdjudicationError):
        record_composite_review(
            proposed,
            state=CompositeAdjudicationState.PRIMARY_ACCEPTED,
            review_note="Invalid because primary has no observation.",
        )
    reviewed = record_composite_review(
        proposed,
        state=CompositeAdjudicationState.SECONDARY_ACCEPTED,
        review_note="Identity and expected session were independently reviewed.",
    )
    assert selected_provider_bar(reviewed) is stooq


def test_disagreement_remains_unpromotable_until_reviewed() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    proposed = propose_composite_adjudication(
        _row(CompositeCoverageState.BOTH_DISAGREE, a=alpha, b=stooq)
    )
    assert proposed.state is CompositeAdjudicationState.DISCREPANCY_REVIEW_REQUIRED
    reviewed = record_composite_review(
        proposed,
        state=CompositeAdjudicationState.REJECTED,
        review_note="Difference remains unresolved after source review.",
    )
    assert reviewed.is_final
    assert not reviewed.is_promotable


def test_final_decision_cannot_be_silently_rewritten() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    decision = propose_composite_adjudication(
        _row(CompositeCoverageState.BOTH_AGREE, a=alpha, b=stooq)
    )
    with pytest.raises(InvalidCompositeAdjudicationError):
        record_composite_review(
            decision,
            state=CompositeAdjudicationState.SECONDARY_ACCEPTED,
            review_note="Attempted rewrite.",
        )
