from __future__ import annotations

from trade_scout.app.strategy_builder_research_memory import STRATEGY_BUILDER_RESEARCH_MEMORY_JS


def test_research_memory_asset_adds_brain_first_workflow_and_resume() -> None:
    assert "Research brain — working session" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Choose the research thread before you iterate" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Resume last session" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "last_url" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "trade-scout:research-brain:active" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS


def test_research_memory_asset_warns_on_duplicate_configuration_without_optimizing() -> None:
    assert (
        "This exact configuration has already been run in this brain"
        in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    )
    assert "Change one declared parameter" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "rather than changing several settings at once" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "last_run_fingerprint" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS


def test_research_memory_asset_routes_saved_runs_to_selected_brain() -> None:
    assert "Add this run to the selected research brain" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert 'params.set("brain", selectedBrain)' in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "rememberCurrentWork(id)" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS


def test_research_memory_asset_discovers_brains_and_honors_brain_handoff() -> None:
    assert 'a[href^="/research/brains?brain="]' in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert 'searchParams.get("brain")' in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "requestedBrain" in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert 'url.searchParams.set("brain", select.value)' in STRATEGY_BUILDER_RESEARCH_MEMORY_JS
