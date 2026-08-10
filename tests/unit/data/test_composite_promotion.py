from datetime import date

import pytest

from trade_scout.data.composite_adjudication import (
    CompositeAdjudicationState,
    propose_composite_adjudication,
    record_composite_review,
)
from trade_scout.data.composite_evidence import CompositeCoverageState, CompositeEvidenceRow
from trade_scout.data.composite_promotion import (
    COMPOSITE_CANONICAL_PROVIDER_ID,
    CompositeCanonicalizationError,
    canonicalize_composite_decisions,
)
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    SecurityType,
)
from trade_scout.data.provider import ProviderDailyBar


def _instrument() -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId("instrument:spy"),
        primary_symbol="SPY",
        name="SPDR S&P 500 ETF Trust",
        exchange="NYSE ARCA",
        security_type=SecurityType.ETF,
        currency="USD",
        first_trade_date=date(1993, 1, 29),
        delisting_date=None,
        provider_ids={
            "alpha_vantage": "alpha_vantage:symbol:SPY",
            "stooq": "stooq:spy",
        },
    )


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
) -> CompositeEvidenceRow:
    return CompositeEvidenceRow(
        instrument_id=InstrumentId("instrument:spy"),
        trade_date=date(2026, 1, 2),
        provider_a_id="alpha_vantage",
        provider_b_id="stooq",
        state=state,
        provider_a_bar=alpha,
        provider_b_bar=stooq,
    )


def test_corroborated_row_uses_composite_identity_but_retains_alpha_source() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    decision = propose_composite_adjudication(
        _row(CompositeCoverageState.BOTH_AGREE, alpha=alpha, stooq=stooq)
    )

    result = canonicalize_composite_decisions(
        (decision,),
        instruments=(_instrument(),),
        dataset_version=DatasetVersion("ab-v0.1"),
    )

    assert result.bars[0].provider_id == COMPOSITE_CANONICAL_PROVIDER_ID
    assert result.provenance[0].selected_source_provider_id == "alpha_vantage"
    assert result.provenance[0].corroborating_provider_ids == ("alpha_vantage", "stooq")
    assert result.provenance[0].included


def test_reviewed_stooq_gap_fill_retains_stooq_as_selected_source() -> None:
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    proposed = propose_composite_adjudication(
        _row(CompositeCoverageState.B_ONLY, alpha=None, stooq=stooq)
    )
    decision = record_composite_review(
        proposed,
        state=CompositeAdjudicationState.SECONDARY_ACCEPTED,
        review_note="Expected session and canonical identity independently confirmed.",
    )

    result = canonicalize_composite_decisions(
        (decision,),
        instruments=(_instrument(),),
        dataset_version=DatasetVersion("ab-v0.1"),
    )

    assert result.bars[0].provider_id == COMPOSITE_CANONICAL_PROVIDER_ID
    assert result.provenance[0].selected_source_provider_id == "stooq"
    assert result.provenance[0].corroborating_provider_ids == ("stooq",)


def test_rejected_disagreement_is_preserved_without_canonical_bar() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    stooq = _bar("stooq", "stooq:spy", "SPY.US")
    proposed = propose_composite_adjudication(
        _row(CompositeCoverageState.BOTH_DISAGREE, alpha=alpha, stooq=stooq)
    )
    decision = record_composite_review(
        proposed,
        state=CompositeAdjudicationState.REJECTED,
        review_note="Unresolved source discrepancy.",
    )

    result = canonicalize_composite_decisions(
        (decision,),
        instruments=(_instrument(),),
        dataset_version=DatasetVersion("ab-v0.1"),
    )

    assert result.bars == ()
    assert not result.provenance[0].included
    assert result.provenance[0].selected_source_provider_id is None


def test_review_required_decision_cannot_enter_canonicalization() -> None:
    alpha = _bar("alpha_vantage", "alpha_vantage:symbol:SPY", "SPY")
    decision = propose_composite_adjudication(
        _row(CompositeCoverageState.A_ONLY, alpha=alpha, stooq=None)
    )
    with pytest.raises(CompositeCanonicalizationError, match="every decision to be final"):
        canonicalize_composite_decisions(
            (decision,),
            instruments=(_instrument(),),
            dataset_version=DatasetVersion("ab-v0.1"),
        )
