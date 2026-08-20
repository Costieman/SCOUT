from trade_scout.app.research_sequence_guidance import guide_research_sequence
from trade_scout.statistics.exit_research import ExitResearchComparison


def test_exit_work_should_be_preceded_by_entry_efficacy() -> None:
    comparison = ExitResearchComparison(
        horizon=20,
        complete_event_count=100,
        event_population_fingerprint="fixture",
        policy_summaries=(),
        warnings=(),
    )
    guidance = guide_research_sequence(comparison)
    assert guidance.stage == "ENTRY_EFFICACY"
    assert "entry" in guidance.headline.lower()
    assert "stops or targets" in guidance.rationale
