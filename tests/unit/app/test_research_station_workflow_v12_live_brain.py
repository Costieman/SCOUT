from trade_scout.app import research_station_workflow_v12 as workflow


def test_live_brain_asset_queries_current_intelligence() -> None:
    source = workflow._live_brain_guidance_js()

    assert "/research/brains/intelligence?brain=" in source
    assert 'cache: "no-store"' in source
    assert "evidenceRevision" in source
    assert "brain-evidence-changed" in source


def test_live_brain_endpoint_fails_closed_when_workbench_has_no_recorder() -> None:
    response = workflow._build_live_research_response(
        "/research/brains/intelligence?brain=brain-a",
        None,  # type: ignore[arg-type]
        experiment_recorder=None,
    )

    assert response.status_code.value == 503
    assert response.content_type.startswith("application/json")
    assert b"not configured" in response.body
