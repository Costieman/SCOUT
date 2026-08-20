from pathlib import Path


def test_workbench_script_uses_brain_aware_research_sequence_v12_runtime() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "research_station_workflow_v12" in source
    assert "Research Station run path: brain-aware-research-sequence-v12" in source
    assert (
        "configure_research_station_runtime(experiment_root=experiment_root, brain_root=brain_root)"
        in source
    )
    assert "research_station_workflow_v11" not in source
