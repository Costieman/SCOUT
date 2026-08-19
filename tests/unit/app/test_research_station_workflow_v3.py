from __future__ import annotations

from trade_scout.app import research_station_workflow_v3 as workflow


def test_run_marker_overrides_preview_marker() -> None:
    query = "suite=TS-S01-CONSOLIDATION-BREAKOUT&load_only=1&execute_run=1&horizon=20"
    cleaned = workflow._without_runtime_markers(query)
    assert "load_only" not in cleaned
    assert "execute_run" not in cleaned
    assert "suite=TS-S01-CONSOLIDATION-BREAKOUT" in cleaned
    assert "horizon=20" in cleaned


def test_explicit_run_button_uses_request_submit_pipeline() -> None:
    asset = workflow._RESEARCH_STATION_V3_JS
    assert 'run.type = "button"' in asset
    assert "form.requestSubmit(submitter)" in asset
    assert 'marker.name = "execute_run"' in asset
    assert 'run.textContent = "Running…"' in asset


def test_loaded_suite_entry_family_is_preserved() -> None:
    asset = workflow._RESEARCH_STATION_V3_JS
    assert 'searchParams.get("entry_family")' in asset
    assert 'input[name="entry_family"]' in asset
    assert "entryFamily.value = requestedFamily" in asset
