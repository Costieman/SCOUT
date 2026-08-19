from pathlib import Path


def test_workbench_script_uses_stable_v5_runtime_with_lifecycle_fix() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v5" in source
    assert "Research Station run path: native-v5-lifecycle-fix" in source
    assert "research_station_workflow_v6" not in source
