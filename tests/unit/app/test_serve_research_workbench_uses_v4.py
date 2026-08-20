from pathlib import Path


def test_workbench_script_uses_guided_research_sequence_v11_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v11" in source
    assert "Research Station run path: guided-research-sequence-v11" in source
    assert "research_station_workflow_v10" not in source
