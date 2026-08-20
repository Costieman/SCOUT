from trade_scout.app import research_station_workflow_v10 as workflow


def test_iterative_runtime_contains_explicit_run_next_path() -> None:
    source = workflow._ITERATIVE_NEXT_STEP_JS
    assert "strategic-run-next" in source
    assert "form.requestSubmit()" in source
    assert "sweep-variable" in source
    assert "sweep-from" in source
    assert "sweep-to" in source
    assert "sweep-step" in source
    assert "Nothing was run" in source
