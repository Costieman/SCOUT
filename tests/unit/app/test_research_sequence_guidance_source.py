from trade_scout.app.research_sequence_guidance import (
    ResearchSequenceEvidence,
    guide_research_sequence_from_evidence,
)


def test_empty_evidence_starts_with_entry_efficacy() -> None:
    guidance = guide_research_sequence_from_evidence(ResearchSequenceEvidence())
    assert guidance.stage == "ENTRY_EFFICACY"
    assert "entry" in guidance.headline.lower()
