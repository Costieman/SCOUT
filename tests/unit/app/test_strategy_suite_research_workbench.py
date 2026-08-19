from __future__ import annotations

from trade_scout.app.strategy_builder_research_memory import STRATEGY_BUILDER_RESEARCH_MEMORY_JS


def test_phase7_exposes_twenty_suite_catalog_in_research_station() -> None:
    asset = STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Strategy suite" in asset
    assert "Load suite into Research Station" in asset
    assert "TS-S01-CONSOLIDATION-BREAKOUT" in asset
    assert "TS-S20-SHORT-TERM-REVERSAL" in asset
    assert asset.count('"id":"TS-S') == 20


def test_phase7_preserves_truthful_ready_partial_blocked_states() -> None:
    asset = STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert '"status":"ready"' in asset
    assert '"status":"partial"' in asset
    assert '"status":"blocked"' in asset
    assert "Suite not executable yet" in asset
    assert "READY suites can populate the current builder" in asset


def test_phase7_suite_launch_preserves_selected_research_brain() -> None:
    asset = STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert 'url.searchParams.set("suite", suite.id)' in asset
    assert 'url.searchParams.set("brain", brain)' in asset
    assert "activeBrainId()" in asset


def test_phase8_adds_one_dimension_iteration_workflow() -> None:
    asset = STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Controlled next iteration" in asset
    assert "Change one declared suite dimension" in asset
    assert "all other settings remain frozen" in asset
    assert "Prepare one-change run" in asset
    assert "target.searchParams.set(parameter, next)" in asset


def test_phase8_rejects_identical_or_unresolved_iteration() -> None:
    asset = STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "An identical configuration is not a new iteration" in asset
    assert "That dimension is not yet machine-resolved" in asset
    assert "option.disabled = !parameter" in asset
