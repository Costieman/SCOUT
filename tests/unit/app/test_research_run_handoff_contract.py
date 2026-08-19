from trade_scout.app import research_station_workflow_v4 as v4
from trade_scout.app import research_station_workflow_v5 as v5


def test_v4_handoff_and_v5_diagnostic_have_distinct_success_semantics() -> None:
    assert 'status.textContent = "Request accepted — starting research…"' in v4._RESEARCH_STATION_V4_JS
    assert 'statusText.startsWith("Request accepted")' in v5._RESEARCH_STATION_V5_JS
    assert "window.location.assign(destination)" in v4._RESEARCH_STATION_V4_JS
