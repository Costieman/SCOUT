"""Live, deterministic synthesis of one Research Brain's preserved evidence.

The intelligence layer interprets immutable experiment evidence; it never mutates experiments,
selects production rules, or promotes a strategy.  Its first responsibility is to turn a Brain
from a collection of runs into an explicit research-state summary that can be recomputed whenever
Brain membership changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from trade_scout.app.research_brain_review import ResearchBrainReview, build_research_brain_review
from trade_scout.app.research_sequence_guidance import (
    ResearchSequenceGuidance,
    guide_research_sequence_from_brain,
)

if TYPE_CHECKING:
    from trade_scout.app.research_brain_service import ResearchBrainView


@dataclass(frozen=True, slots=True)
class ResearchBrainIntelligence:
    """Current derived research state for one Brain."""

    brain_id: str
    experiment_count: int
    evidence_revision: str
    review: ResearchBrainReview
    guidance: ResearchSequenceGuidance
    supported_relationships: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    contradictions: tuple[str, ...]
    rejected_or_failed_threads: tuple[str, ...]


def synthesize_research_brain(view: ResearchBrainView) -> ResearchBrainIntelligence:
    """Recompute Brain intelligence from the current checksum-verified membership view."""

    review = build_research_brain_review(view.snapshot, view.experiments)
    guidance = guide_research_sequence_from_brain(view)
    return ResearchBrainIntelligence(
        brain_id=view.snapshot.definition.brain_id,
        experiment_count=len(view.snapshot.memberships),
        evidence_revision=_evidence_revision(view),
        review=review,
        guidance=guidance,
        supported_relationships=_supported_relationships(review),
        unresolved_questions=review.next_questions,
        contradictions=_contradictions(review),
        rejected_or_failed_threads=_failed_threads(review),
    )


def _evidence_revision(view: ResearchBrainView) -> str:
    """Return a stable revision token that changes when Brain evidence membership changes."""

    memberships = sorted(
        (
            membership.experiment_id,
            membership.experiment_manifest_checksum,
        )
        for membership in view.snapshot.memberships
    )
    return "|".join(f"{experiment_id}:{checksum}" for experiment_id, checksum in memberships)


def _supported_relationships(review: ResearchBrainReview) -> tuple[str, ...]:
    """Expose only descriptive relationships already stated by the conservative Brain review."""

    return tuple(
        finding
        for finding in review.findings
        if "highest historical cell" in finding or "parameter sweep" in finding
    )


def _contradictions(review: ResearchBrainReview) -> tuple[str, ...]:
    """Surface evidence tensions without inventing statistical conclusions."""

    tensions: list[str] = []
    if review.drift_warning_count:
        tensions.append(
            "Some preserved experiments fall outside the Brain's declared focus boundary; "
            "their evidence should not be silently pooled with in-focus work."
        )
    for caution in review.cautions:
        if "uneven sample support" in caution:
            tensions.append(caution)
    return tuple(tensions)


def _failed_threads(review: ResearchBrainReview) -> tuple[str, ...]:
    if review.failed_count == 0:
        return ()
    return (
        f"{review.failed_count} failed experiment(s) remain part of the research history and "
        "must not disappear from subsequent Brain reasoning.",
    )


__all__ = ["ResearchBrainIntelligence", "synthesize_research_brain"]
