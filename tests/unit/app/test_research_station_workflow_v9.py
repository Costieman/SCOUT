from trade_scout.app import research_station_workflow_v9 as workflow
from trade_scout.app import research_workbench_console as console


def test_v9_preserves_v8_operator_controlled_popup_runtime() -> None:
    workflow.configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "strategic-next-step-modal" in asset
    assert "customValidationSource" in asset
    assert "Strategy suite" in asset
    assert "research-brain-session-card" in asset


def test_v9_shared_renderer_exposes_robustness_contract() -> None:
    source = workflow._render_next_steps_v9
    assert "render_strategic_next_step_html" in source.__code__.co_names
    assert "analyze_strategic_next_steps" in source.__code__.co_names
