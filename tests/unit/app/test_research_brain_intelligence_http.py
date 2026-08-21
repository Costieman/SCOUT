from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from trade_scout.app import research_brain_intelligence_http as http


def test_live_intelligence_endpoint_requires_one_brain_query() -> None:
    status, payload = http.build_research_brain_intelligence_json("", SimpleNamespace())

    assert status.value == 400
    assert "required exactly once" in payload


def test_live_intelligence_endpoint_serializes_current_service_state(monkeypatch) -> None:
    guidance = SimpleNamespace(
        stage="HOLDING_HORIZON",
        headline="Test horizon next.",
        rationale="Entry neighborhood evidence exists.",
        next_dimension="Compare 20 and 60 sessions.",
        evidence_source="research_brain",
    )
    review = SimpleNamespace(
        readiness_label="RESEARCHING",
        readiness_explanation="More evidence needed.",
    )
    intelligence = SimpleNamespace(
        brain_id="brain-a",
        evidence_revision="exp-a:checksum-a|exp-b:checksum-b",
        experiment_count=2,
        guidance=guidance,
        supported_relationships=("broad region observed",),
        unresolved_questions=("test horizon",),
        contradictions=("uneven sample support",),
        rejected_or_failed_threads=("one failed run retained",),
        review=review,
    )
    current_view = SimpleNamespace(snapshot=SimpleNamespace())

    class FakeService:
        def __init__(self, *, experiment_root, brain_root) -> None:
            assert str(experiment_root).endswith("experiments")
            assert str(brain_root).endswith("brains")

        def detail(self, brain_id: str):
            assert brain_id == "brain-a"
            return current_view

    monkeypatch.setattr(http, "ResearchBrainWorkbenchService", FakeService)
    monkeypatch.setattr(
        http,
        "synthesize_research_brain",
        lambda view: intelligence if view is current_view else None,
    )
    recorder = SimpleNamespace(experiment_root=Path("runtime/experiments"))

    status, payload = http.build_research_brain_intelligence_json("brain=brain-a", recorder)

    assert status.value == 200
    assert '"stage":"HOLDING_HORIZON"' in payload
    assert '"evidence_revision":"exp-a:checksum-a|exp-b:checksum-b"' in payload
    assert '"contradictions":["uneven sample support"]' in payload
