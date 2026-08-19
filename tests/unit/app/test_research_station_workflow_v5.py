from trade_scout.app import research_station_workflow_v5 as workflow
from trade_scout.app import research_workbench_console as console


def test_v5_validates_explicitly_before_request_submit() -> None:
    source = workflow._RESEARCH_STATION_V5_JS
    assert 'run.type = "button"' in source
    assert "oldRun.replaceWith(run)" in source
    assert "form.reportValidity()" in source
    assert "form.requestSubmit()" in source
    assert "Browser validation blocked the request before a submit event could occur" in source
    assert 'form.addEventListener("submit"' in source
    assert "event.defaultPrevented" in source
    assert "Research did not start" in source


def test_v5_waits_for_persistent_run_dock_before_installing() -> None:
    source = workflow._RESEARCH_STATION_V5_JS
    assert "scheduleNativeRunInstall" in source
    assert 'document.addEventListener("DOMContentLoaded"' in source
    assert "if (installNativeRun()) return" in source
    assert "attempts < 80" in source
    assert "MutationObserver" not in source
    assert 'document.addEventListener("click"' not in source


def test_v5_preserves_suite_and_brain_integration_in_combined_asset() -> None:
    workflow.configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Strategy suite" in asset
    assert "TS-S01-CONSOLIDATION-BREAKOUT" in asset
    assert "research-brain-session-card" in asset
    assert 'fetch("/research/brains"' in asset
    assert "+ New Brain" in asset
    assert "Run path: native-v5-validation-fix" in asset
    assert "Run path: lifecycle-v6" not in asset


def test_v5_exposes_runtime_marker_for_operator_debugging() -> None:
    source = workflow._RESEARCH_STATION_V5_JS
    assert "Run path: native-v5-validation-fix" in source
    assert 'input[name="execute_run"]' in source
