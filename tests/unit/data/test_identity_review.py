from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trade_scout.data.contracts import SecurityType
from trade_scout.data.identity_review import (
    IdentityReviewDecision,
    IdentityReviewError,
    ReferenceIdentityReview,
    apply_reference_identity_review,
)
from trade_scout.data.instrument_master import instrument_from_primary_provider
from trade_scout.data.provider import ProviderInstrument
from trade_scout.data.reference_reconciliation import (
    ReferenceCandidateState,
    ReferenceMatchCandidate,
)


def _market_instrument() -> ProviderInstrument:
    return ProviderInstrument(
        provider_id="alpha_vantage",
        provider_instrument_id="AAPL",
        symbol="AAPL",
        name="Apple Inc",
        exchange="NASDAQ",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        active=True,
        first_trade_date=None,
        end_date=None,
        source_fields={},
    )


def _candidate(state: ReferenceCandidateState = ReferenceCandidateState.EXACT_SYMBOL_EXCHANGE):
    return ReferenceMatchCandidate(
        market_provider_id="alpha_vantage",
        market_provider_instrument_id="AAPL",
        symbol="AAPL",
        exchange="NASDAQ",
        state=state,
        reference_provider_ids=("sec_edgar",),
        reference_provider_instrument_ids=("sec_edgar:cik:320193:ticker:AAPL",),
        evidence=("exact current symbol match", "exact normalized exchange match"),
    )


def _review(
    decision: IdentityReviewDecision = IdentityReviewDecision.APPROVED,
) -> ReferenceIdentityReview:
    return ReferenceIdentityReview(
        decision_id="identity-review-0001",
        decision=decision,
        market_provider_id="alpha_vantage",
        market_provider_instrument_id="AAPL",
        reference_provider_id="sec_edgar",
        reference_provider_instrument_id="sec_edgar:cik:320193:ticker:AAPL",
        reviewer="trade-scout-identity-review",
        decided_at=datetime(2026, 8, 9, 7, 30, tzinfo=UTC),
        evidence_refs=("raw/sec/current-association-batch", "review/issuer-security-check"),
        rationale="Current ticker/exchange association independently reviewed for this security.",
    )


def test_approved_exact_candidate_links_reference_identity_without_mutating_input() -> None:
    original = instrument_from_primary_provider(_market_instrument())

    result = apply_reference_identity_review(
        (original,),
        candidate=_candidate(),
        review=_review(),
    )

    assert original.provider_ids == {"alpha_vantage": "AAPL"}
    assert result.instrument_id == original.instrument_id
    assert result.decision_id == "identity-review-0001"
    assert result.updated_instruments[0].provider_ids == {
        "alpha_vantage": "AAPL",
        "sec_edgar": "sec_edgar:cik:320193:ticker:AAPL",
    }


def test_symbol_only_candidate_cannot_be_promoted_even_with_approval() -> None:
    original = instrument_from_primary_provider(_market_instrument())

    with pytest.raises(IdentityReviewError, match="exact current symbol/exchange"):
        apply_reference_identity_review(
            (original,),
            candidate=_candidate(ReferenceCandidateState.SYMBOL_ONLY),
            review=_review(),
        )


def test_rejected_review_never_modifies_instrument_master() -> None:
    original = instrument_from_primary_provider(_market_instrument())

    with pytest.raises(IdentityReviewError, match="rejected"):
        apply_reference_identity_review(
            (original,),
            candidate=_candidate(),
            review=_review(IdentityReviewDecision.REJECTED),
        )

    assert original.provider_ids == {"alpha_vantage": "AAPL"}


def test_review_must_match_exact_candidate_reference_identity() -> None:
    original = instrument_from_primary_provider(_market_instrument())
    review = ReferenceIdentityReview(
        decision_id="identity-review-0002",
        decision=IdentityReviewDecision.APPROVED,
        market_provider_id="alpha_vantage",
        market_provider_instrument_id="AAPL",
        reference_provider_id="sec_edgar",
        reference_provider_instrument_id="sec_edgar:cik:999:ticker:AAPL",
        reviewer="reviewer",
        decided_at=datetime(2026, 8, 9, 7, 30, tzinfo=UTC),
        evidence_refs=("evidence/1",),
        rationale="Mismatch test.",
    )

    with pytest.raises(IdentityReviewError, match="reference identity"):
        apply_reference_identity_review((original,), candidate=_candidate(), review=review)


def test_review_requires_auditable_evidence_and_timezone() -> None:
    with pytest.raises(ValueError, match="evidence"):
        ReferenceIdentityReview(
            decision_id="identity-review-0003",
            decision=IdentityReviewDecision.APPROVED,
            market_provider_id="alpha_vantage",
            market_provider_instrument_id="AAPL",
            reference_provider_id="sec_edgar",
            reference_provider_instrument_id="sec-edgar-id",
            reviewer="reviewer",
            decided_at=datetime(2026, 8, 9, 7, 30, tzinfo=UTC),
            evidence_refs=(),
            rationale="No evidence should fail.",
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        ReferenceIdentityReview(
            decision_id="identity-review-0004",
            decision=IdentityReviewDecision.APPROVED,
            market_provider_id="alpha_vantage",
            market_provider_instrument_id="AAPL",
            reference_provider_id="sec_edgar",
            reference_provider_instrument_id="sec-edgar-id",
            reviewer="reviewer",
            decided_at=datetime(2026, 8, 9, 7, 30),
            evidence_refs=("evidence/1",),
            rationale="Naive timestamps should fail.",
        )
