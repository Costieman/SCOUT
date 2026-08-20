from pathlib import Path


def test_workbench_script_uses_strategic_next_step_v8_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v8" in source
    assert "Research Station run path: strategic-next-step-v8" in source
    assert "research_station_workflow_v7" not in source
