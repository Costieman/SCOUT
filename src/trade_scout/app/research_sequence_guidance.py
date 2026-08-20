"""Plain-English research-order guidance for Strategy Builder experiments."""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.statistics.exit_research import ExitResearchComparison


@dataclass(frozen=True, slots=True)
class ResearchSequenceGuidance:
    stage: str
    headline: str
    rationale: str
    next_dimension: str


def guide_research_sequence(
    comparison: ExitResearchComparison,
    *,
    has_entry_sweep: bool = False,
) -> ResearchSequenceGuidance:
    """Recommend the highest-information research stage without enforcing it."""

    if not has_entry_sweep:
        return ResearchSequenceGuidance(
            stage="ENTRY_EFFICACY",
            headline="Establish the entry before optimizing trade management.",
            rationale=(
                "This run contains exit-policy evidence, but SCOUT has not yet established that the "
                "entry itself creates a useful historical population. Optimizing stops or targets "
                "before testing entry efficacy can polish noise rather than improve a real signal."
            ),
            next_dimension=(
                "First test the entry condition and its Section 5 indicator parameter against the "
                "hold outcome. Then check whether the result survives neighboring parameter values."
            ),
        )

    return ResearchSequenceGuidance(
        stage="ENTRY_ROBUSTNESS",
        headline="Entry evidence exists; test robustness before complex exits.",
        rationale=(
            "The next useful question is whether the entry effect survives nearby parameter values "
            "and sensible holding horizons rather than depending on one historical cell."
        ),
        next_dimension=(
            "Resolve the entry neighborhood, then test holding horizon. Move into stops, targets and "
            "execution sensitivity only after the signal remains useful across those checks."
        ),
    )


__all__ = ["ResearchSequenceGuidance", "guide_research_sequence"]
