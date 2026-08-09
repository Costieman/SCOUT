"""Reviewed promotion of non-authoritative reference candidates into provider identity links.

Candidate generation and canonical identity mutation remain separate operations. A current-reference
match can only be promoted after an explicit decision cites external evidence and the candidate has
exact current symbol/exchange agreement. The decision links the reference provider association to
an existing canonical instrument; it does not create a new instrument or infer historical symbol
continuity.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from trade_scout.data.contracts import InstrumentId, InstrumentRecord
from trade_scout.data.instrument_master import (
    InstrumentIdentityConflictError,
    link_provider_identity,
    resolve_provider_identity,
)
from trade_scout.data.reference_reconciliation import (
    ReferenceCandidateState,
    ReferenceMatchCandidate,
)


class IdentityReviewDecision(StrEnum):
    """Explicit disposition of one non-authoritative reference candidate."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ReferenceIdentityReview:
    """Auditable human/review-process decision for one exact reference candidate."""

    decision_id: str
    decision: IdentityReviewDecision
    market_provider_id: str
    market_provider_instrument_id: str
    reference_provider_id: str
    reference_provider_instrument_id: str
    reviewer: str
    decided_at: datetime
    evidence_refs: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        for field, value in (
            ("decision_id", self.decision_id),
            ("market_provider_id", self.market_provider_id),
            ("market_provider_instrument_id", self.market_provider_instrument_id),
            ("reference_provider_id", self.reference_provider_id),
            ("reference_provider_instrument_id", self.reference_provider_instrument_id),
            ("reviewer", self.reviewer),
            ("rationale", self.rationale),
        ):
            if not value.strip():
                raise ValueError(f"{field} must be non-empty")
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("decided_at must be timezone-aware")
        if not self.evidence_refs or any(not item.strip() for item in self.evidence_refs):
            raise ValueError("identity review must cite non-empty evidence references")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("identity review evidence references must not contain duplicates")


@dataclass(frozen=True, slots=True)
class IdentityLinkResult:
    """Result of applying one approved review without mutating the input snapshot."""

    instrument_id: InstrumentId
    updated_instruments: tuple[InstrumentRecord, ...]
    decision_id: str


class IdentityReviewError(ValueError):
    """Raised when a review cannot safely authorize a canonical provider link."""


def apply_reference_identity_review(
    instruments: Iterable[InstrumentRecord],
    *,
    candidate: ReferenceMatchCandidate,
    review: ReferenceIdentityReview,
) -> IdentityLinkResult:
    """Apply one exact approved current-reference link to an immutable instrument collection.

    Only ``EXACT_SYMBOL_EXCHANGE`` candidates are eligible for promotion. ``SYMBOL_ONLY`` evidence
    remains useful for investigation but is deliberately insufficient for an identity mutation.
    Rejected reviews never modify the instrument collection.
    """

    records = tuple(instruments)
    _validate_review_matches_candidate(candidate, review)
    if review.decision is IdentityReviewDecision.REJECTED:
        raise IdentityReviewError("rejected identity review cannot modify the instrument master")
    if candidate.state is not ReferenceCandidateState.EXACT_SYMBOL_EXCHANGE:
        raise IdentityReviewError(
            "only exact current symbol/exchange candidates may be promoted after review"
        )
    if not candidate.has_unique_candidate:
        raise IdentityReviewError("identity review requires exactly one reference candidate")

    instrument_id = resolve_provider_identity(
        records,
        provider_id=candidate.market_provider_id,
        provider_instrument_id=candidate.market_provider_instrument_id,
    )
    if instrument_id is None:
        raise IdentityReviewError("market-provider identity is not present in the canonical master")

    matches = [item for item in records if item.instrument_id == instrument_id]
    if len(matches) != 1:
        raise InstrumentIdentityConflictError(
            f"canonical instrument {instrument_id} is not uniquely represented"
        )
    current = matches[0]
    updated = link_provider_identity(
        current,
        provider_id=review.reference_provider_id,
        provider_instrument_id=review.reference_provider_instrument_id,
    )
    output = tuple(
        sorted(
            (replace(item) if item.instrument_id != instrument_id else updated for item in records),
            key=lambda item: str(item.instrument_id),
        )
    )
    return IdentityLinkResult(
        instrument_id=instrument_id,
        updated_instruments=output,
        decision_id=review.decision_id,
    )


def _validate_review_matches_candidate(
    candidate: ReferenceMatchCandidate,
    review: ReferenceIdentityReview,
) -> None:
    if review.market_provider_id != candidate.market_provider_id or (
        review.market_provider_instrument_id != candidate.market_provider_instrument_id
    ):
        raise IdentityReviewError("review market identity does not match the candidate")

    reference_pairs = set(
        zip(
            candidate.reference_provider_ids,
            candidate.reference_provider_instrument_ids,
            strict=True,
        )
    )
    if (
        review.reference_provider_id,
        review.reference_provider_instrument_id,
    ) not in reference_pairs:
        raise IdentityReviewError("review reference identity does not match the candidate")
