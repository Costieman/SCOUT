from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_entry_sweep_controls import STRATEGY_BUILDER_ENTRY_SWEEP_JS
from trade_scout.app.strategy_builder_entry_sweep_http import is_entry_sweep_query


def test_entry_sweep_controls_expose_configured_indicator_parameters() -> None:
    assert "Entry indicator parameters" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Period / lookback" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Standard deviations" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Fast EMA period" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Slow EMA period" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Signal EMA period" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "UNDER TEST IN SECTION 5" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "point-in-time child definition" in STRATEGY_BUILDER_ENTRY_SWEEP_JS


def test_entry_sweep_observes_only_rule_row_structure() -> None:
    assert "scheduleRebuild" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert ").observe(rules, {childList: true});" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "subtree: true" not in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "mutationOnlyTouchesSweepBadges" not in STRATEGY_BUILDER_ENTRY_SWEEP_JS


def test_entry_sweep_reclaims_shared_section5_inputs_after_exit_sweep_handler() -> None:
    assert "syncEntrySweep(false, true)" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "for (const input of [from, to, step])" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "preserveValues" in STRATEGY_BUILDER_ENTRY_SWEEP_JS


def test_entry_sweep_has_temporary_interactive_resource_guard() -> None:
    assert "MAX_INTERACTIVE_ENTRY_VALUES = 8" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "temporarily capped" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "current interactive safety limit" in STRATEGY_BUILDER_ENTRY_SWEEP_JS


def test_entry_sweep_makes_exit_policy_state_explicit() -> None:
    assert "entry-sweep-exits-inactive" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "exits are not applied in this run" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Exit candidates shown below are preserved for later experiments" in STRATEGY_BUILDER_ENTRY_SWEEP_JS
    assert "Entry-indicator sweeps create a separate point-in-time child population" in STRATEGY_BUILDER_ENTRY_SWEEP_JS


def test_entry_sweep_query_detection_is_explicit() -> None:
    assert is_entry_sweep_query(
        "entry_sweep_feature=pi__moving_average__ma_distance_pct__close__p200__sma"
    )
    assert not is_entry_sweep_query("sweep_variable=fixed&sweep_from=1&sweep_to=10&sweep_step=1")


def test_workbench_serves_entry_sweep_asset_without_analytical_sources() -> None:
    response = build_research_workbench_response(
        "/assets/strategy-builder-entry-sweep.js",
        cast(LocalConsoleConfig, object()),
    )

    assert response.status_code == 200
    assert response.content_type == "text/javascript; charset=utf-8"
    assert response.body.decode("utf-8") == STRATEGY_BUILDER_ENTRY_SWEEP_JS
