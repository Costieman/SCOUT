from pathlib import Path


def test_workbench_script_uses_generalized_strategic_analysis_v9_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v9" in source
    assert "Research Station run path: generalized-strategic-analysis-v9" in source
    assert "research_station_workflow_v8" not in source
