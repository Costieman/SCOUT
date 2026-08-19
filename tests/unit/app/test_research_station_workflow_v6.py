from trade_scout.app import research_station_workflow_v6 as workflow


def test_v6_handles_late_run_dock_creation() -> None:
    source = workflow._RESEARCH_STATION_V6_JS
    assert "MutationObserver" in source
    assert "installDock" in source
    assert "#strategy-run-dock button.primary" in source
    assert "form.requestSubmit()" in source


def test_v6_exposes_independent_runtime_marker_and_failures() -> None:
    source = workflow._RESEARCH_STATION_V6_JS
    assert "Run path: lifecycle-v6" in source
    assert "research-run-runtime-v6" in source
    assert "Research did not start" in source
    assert 'input[name="load_only"]' in source
    assert 'input[name="execute_run"]' in source
