from trade_scout.app import research_station_workflow_v4 as workflow


def test_v4_asset_reports_client_and_backend_run_failures() -> None:
    source = workflow._RESEARCH_STATION_V4_JS
    assert "research-run-diagnostic-modal" in source
    assert "event.defaultPrevented" in source
    assert "Nothing was sent to the backend" in source
    assert "run_attempt" in source
    assert "The request reached the backend" in source


def test_v4_asset_serializes_final_form_after_other_submit_handlers() -> None:
    source = workflow._RESEARCH_STATION_V4_JS
    assert "new FormData(form)" in source
    assert 'data.delete("load_only")' in source
    assert 'data.set("execute_run", "1")' in source
    assert "window.location.assign(destination)" in source
