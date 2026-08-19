from trade_scout.app import research_station_workflow_v5 as workflow


def test_v5_uses_native_submit_and_capture_diagnostics() -> None:
    source = workflow._RESEARCH_STATION_V5_JS
    assert 'run.type = "submit"' in source
    assert 'oldRun.replaceWith(run)' in source
    assert 'form.addEventListener("submit"' in source
    assert '}, true);' in source
    assert "event.defaultPrevented" in source
    assert "Research did not start" in source


def test_v5_exposes_runtime_marker_for_operator_debugging() -> None:
    source = workflow._RESEARCH_STATION_V5_JS
    assert "Run path: native-v5" in source
    assert 'input[name="execute_run"]' in source
