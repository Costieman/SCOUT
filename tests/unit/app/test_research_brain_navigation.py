from __future__ import annotations

from trade_scout.app.research_brain_navigation import RESEARCH_BRAIN_NAVIGATION_JS


def test_research_brain_navigation_returns_to_strategy_builder_with_selected_brain() -> None:
    assert "Continue research in Strategy Builder" in RESEARCH_BRAIN_NAVIGATION_JS
    assert "Research from this brain" in RESEARCH_BRAIN_NAVIGATION_JS
    assert "/research/strategy?brain=" in RESEARCH_BRAIN_NAVIGATION_JS
    assert "trade-scout:research-brain:active" in RESEARCH_BRAIN_NAVIGATION_JS


def test_research_brain_navigation_preselects_open_brain_for_add_form() -> None:
    assert 'searchParams.get("brain")' in RESEARCH_BRAIN_NAVIGATION_JS
    assert 'select[name="brain_id"]' in RESEARCH_BRAIN_NAVIGATION_JS
    assert "addSelect.value = preselected" in RESEARCH_BRAIN_NAVIGATION_JS
