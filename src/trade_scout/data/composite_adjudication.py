"""Explicit review gate between A+B evidence and canonical promotion.

The A+B evidence layer describes what Alpha Vantage and Stooq observed. This module
turns that evidence into auditable promotion decisions without averaging feeds,
interpolating missing sessions, or silently choosing a provider.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from trade_scout.data.composite_evidence import CompositeCoverageState, CompositeEvidenceRow
from trade_scout.data.provider import ProviderDailyBar


class CompositeAdjudicationState(StrEnum):
    """Decision state for one A+B instrument/session observation."""

    CORROBORATED = "CORROBORATED"
    GAP_REVIEW_REQUIRED = "GAP_REVIEW_REQUIRED"
    DISCREPANCY_REVIEW_REQUIRED = "DISCREPANCY_REVIEW_REQUIRED"
    PRIMARY_ACCEPTED = "PRIMARY_ACCEPTED"
    SECONDARY_ACCEPTED = "SECONDARY_ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class CompositeAdjudicationDecision:
    """Immutable review state linked directly to one composite-evidence row."""

    evidence: CompositeEvidenceRow
    state: CompositeAdjudicationState
    selected_provider_id: str | None
    review_note: str | None = None

    @property
    def is_final(self) -> bool:
        return self.state in {
            CompositeAdjudicationState.CORROBORATED,
            CompositeAdjudicationState.PRIMARY_ACCEPTED,
            CompositeAdjudicationState.SECONDARY_ACCEPTED,
            CompositeAdjudicationState.REJECTED,
        }

    @property
    def is_promotable(self) -> bool:
        return self.state in {
            CompositeAdjudicationState.CORROBORATED,
            CompositeAdjudicationState.PRIMARY_ACCEPTED,
            CompositeAdjudicationState.SECONDARY_ACCEPTED,
        }


class InvalidCompositeAdjudicationError(ValueError):
    """Raised when review attempts an unsupported or unsafe evidence transition."""


def propose_composite_adjudication(
    evidence: CompositeEvidenceRow,
) -> CompositeAdjudicationDecision:
    """Create the conservative default decision implied by observed A+B evidence."""

    if evidence.state is CompositeCoverageState.BOTH_AGREE:
        return CompositeAdjudicationDecision(
            evidence=evidence,
            state=CompositeAdjudicationState.CORROBORATED,
            selected_provider_id=evidence.provider_a_id,
            review_note="A+B raw OHLCV agree within the configured tolerance",
        )
    if evidence.state is CompositeCoverageState.BOTH_DISAGREE:
        return CompositeAdjudicationDecision(
            evidence=evidence,
            state=CompositeAdjudicationState.DISCREPANCY_REVIEW_REQUIRED,
            selected_provider_id=None,
        )
    return CompositeAdjudicationDecision(
        evidence=evidence,
        state=CompositeAdjudicationState.GAP_REVIEW_REQUIRED,
        selected_provider_id=None,
    )


def record_composite_review(
    decision: CompositeAdjudicationDecision,
    *,
    state: CompositeAdjudicationState,
    review_note: str,
) -> CompositeAdjudicationDecision:
    """Resolve a review-required decision while preserving the original evidence."""

    if decision.is_final:
        raise InvalidCompositeAdjudicationError(
            f"cannot review finalized composite decision {decision.state}"
        )
    note = review_note.strip()
    if not note:
        raise ValueError("composite adjudication requires a non-empty review note")

    if state is CompositeAdjudicationState.REJECTED:
        return replace(
            decision,
            state=state,
            selected_provider_id=None,
            review_note=note,
        )

    if state is CompositeAdjudicationState.PRIMARY_ACCEPTED:
        if decision.evidence.provider_a_bar is None:
            raise InvalidCompositeAdjudicationError(
                "cannot accept primary provider when no primary observation exists"
            )
        return replace(
            decision,
            state=state,
            selected_provider_id=decision.evidence.provider_a_id,
            review_note=note,
        )

    if state is CompositeAdjudicationState.SECONDARY_ACCEPTED:
        if decision.evidence.provider_b_bar is None:
            raise InvalidCompositeAdjudicationError(
                "cannot accept secondary provider when no secondary observation exists"
            )
        return replace(
            decision,
            state=state,
            selected_provider_id=decision.evidence.provider_b_id,
            review_note=note,
        )

    raise InvalidCompositeAdjudicationError(
        f"review cannot transition {decision.state} to {state}"
    )


def selected_provider_bar(
    decision: CompositeAdjudicationDecision,
) -> ProviderDailyBar:
    """Return the explicitly selected raw bar only after a promotable final decision."""

    if not decision.is_promotable or decision.selected_provider_id is None:
        raise InvalidCompositeAdjudicationError(
            f"composite decision {decision.state} has no promotable provider observation"
        )
    evidence = decision.evidence
    if decision.selected_provider_id == evidence.provider_a_id and evidence.provider_a_bar is not None:
        return evidence.provider_a_bar
    if decision.selected_provider_id == evidence.provider_b_id and evidence.provider_b_bar is not None:
        return evidence.provider_b_bar
    raise InvalidCompositeAdjudicationError(
        "selected provider is inconsistent with the preserved A+B evidence"
    )
