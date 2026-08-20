from pathlib import Path


def test_workbench_script_uses_iterative_strategic_research_v10_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v10" in source
    assert "Research Station run path: iterative-strategic-research-v10" in source
    assert "research_station_workflow_v9" not in source
