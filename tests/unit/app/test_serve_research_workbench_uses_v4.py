from pathlib import Path


def test_workbench_script_imports_v6_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v6" in source
    assert "Research Station run path: lifecycle-v6" in source
