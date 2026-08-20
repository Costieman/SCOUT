from trade_scout.app.research_sequence_guidance import (
    ResearchSequenceEvidence,
    guide_research_sequence_from_evidence,
)


def test_brain_sequence_advances_through_missing_dimensions() -> None:
    guidance = guide_research_sequence_from_evidence(
        ResearchSequenceEvidence(entry_efficacy=True, entry_robustness=True)
    )
    assert guidance.stage == "HOLDING_HORIZON"
    assert guidance.evidence_source == "research_brain"

    guidance = guide_research_sequence_from_evidence(
        ResearchSequenceEvidence(
            entry_efficacy=True,
            entry_robustness=True,
            holding_horizon=True,
        )
    )
    assert guidance.stage == "EXITS_RISK"

    guidance = guide_research_sequence_from_evidence(
        ResearchSequenceEvidence(
            entry_efficacy=True,
            entry_robustness=True,
            holding_horizon=True,
            exits_risk=True,
        )
    )
    assert guidance.stage == "EXECUTION_SENSITIVITY"


def test_complete_brain_sequence_moves_to_validation() -> None:
    guidance = guide_research_sequence_from_evidence(
        ResearchSequenceEvidence(
            experiment_count=12,
            entry_efficacy=True,
            entry_robustness=True,
            holding_horizon=True,
            exits_risk=True,
            execution_sensitivity=True,
        )
    )
    assert guidance.stage == "VALIDATION"
    assert "validation" in guidance.headline.lower()
