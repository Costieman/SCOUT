from pathlib import Path

from trade_scout.app import research_station_workflow_v8 as workflow
from trade_scout.app import research_workbench_console as console


def test_v8_popup_is_operator_controlled_and_never_auto_runs_research() -> None:
    source = workflow._STRATEGIC_NEXT_STEP_JS
    assert 'document.getElementById("strategic-next-step-modal")' in source
    assert "window.setTimeout(show" in source
    assert "Run research" not in source
    assert ".submit(" not in source
    assert "requestSubmit" not in source


def test_v8_preserves_v7_runtime_and_adds_strategic_analysis_asset() -> None:
    workflow.configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "customValidationSource" in asset
    assert "Strategy suite" in asset
    assert "research-brain-session-card" in asset
    assert "strategic-next-step-modal" in asset
    assert "SCOUT research analysis" not in asset


def test_v8_render_contains_direction_range_rationale_and_falsifier() -> None:
    source = Path("src/trade_scout/app/research_station_workflow_v8.py").read_text(encoding="utf-8")
    assert "analyze_strategic_next_steps" in source
    assert "Direction:" in source
    assert "Suggested next range:" in source
    assert "Why:" in source
    assert "What would falsify it:" in source
