from trade_scout.app.research_station_workflow_v12 import _brain_guidance_js


def test_brain_guidance_js_uses_selected_or_active_brain() -> None:
    source = _brain_guidance_js(
        '{"brain_alpha":{"stage":"HOLDING_HORIZON","headline":"H","rationale":"R","next_dimension":"N"}}'
    )
    assert 'searchParams.get("brain")' in source
    assert "trade-scout:research-brain:active" in source
    assert "brain-aware-research-sequence-v12" in source
    assert "research-sequence-headline" in source
    assert "item.next_dimension" in source
