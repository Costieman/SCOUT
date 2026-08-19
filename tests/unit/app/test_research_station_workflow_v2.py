from __future__ import annotations

from trade_scout.app import research_station_workflow_v2 as workflow


def test_suite_load_is_explicit_configuration_preview() -> None:
    asset = workflow._RESEARCH_STATION_V2_JS
    assert 'url.searchParams.set("load_only", "1")' in asset
    assert "event.stopImmediatePropagation()" in asset
    assert "loadSuiteWithoutRunning(suiteId)" in asset


def test_run_action_is_persistent_and_separate_from_section_five() -> None:
    asset = workflow._RESEARCH_STATION_V2_JS
    assert 'dock.id = "strategy-run-dock"' in asset
    assert "position: fixed" in asset
    assert 'run.textContent = "Run research"' in asset
    assert "form.append(dock)" in asset


def test_sweep_locks_only_component_under_test() -> None:
    asset = workflow._RESEARCH_STATION_V2_JS
    assert 'if (component === "stop")' in asset
    assert "if (stopFamily) stopFamily.disabled = true" in asset
    assert "if (targetFamily) targetFamily.disabled = false" in asset
    assert "if (targetFamily) targetFamily.disabled = true" in asset
    assert "if (stopFamily) stopFamily.disabled = false" in asset
    assert "Profit-target settings remain editable." in asset
    assert "Protective-stop settings remain editable." in asset


def test_configuration_preview_marker_is_checked_before_recorded_run() -> None:
    source = workflow._recorded_page_with_configuration_preview.__code__.co_consts
    assert "load_only" in source
