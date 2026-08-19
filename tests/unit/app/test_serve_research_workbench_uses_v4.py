from pathlib import Path


def test_workbench_script_uses_validation_focus_v7_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v7" in source
    assert "Research Station run path: validation-focus-v7" in source
    assert "research_station_workflow_v6" not in source
