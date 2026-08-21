from __future__ import annotations

from types import SimpleNamespace

from trade_scout.app.research_brain_intelligence import synthesize_research_brain
from trade_scout.experiments.contracts import ExperimentStatus


def _view(*, failed_count: int = 0, drift_warning_count: int = 0):
    definition = SimpleNamespace(brain_id="brain-breakout")
    membership = SimpleNamespace(
        experiment_id="exp-1",
        experiment_manifest_checksum="checksum-1",
    )
    snapshot = SimpleNamespace(
        definition=definition,
        memberships=(membership,),
        succeeded_count=1,
        failed_count=failed_count,
        drift_warning_count=drift_warning_count,
    )
    manifest = SimpleNamespace(
        status=ExperimentStatus.SUCCEEDED,
        experiment_id="exp-1",
        definition=SimpleNamespace(
            resolved_configuration={"holding_horizon": 20},
        ),
    )
    experiment = SimpleNamespace(
        manifest=manifest,
        result=None,
        stage_outputs={},
    )
    item = SimpleNamespace(experiment=experiment, integrity_error=None)
    return SimpleNamespace(snapshot=snapshot, experiments=(item,))


def test_synthesis_is_current_and_recommends_next_missing_stage() -> None:
    intelligence = synthesize_research_brain(_view())

    assert intelligence.brain_id == "brain-breakout"
    assert intelligence.experiment_count == 1
    assert intelligence.evidence_revision == "exp-1:checksum-1"
    assert intelligence.guidance.stage == "ENTRY_ROBUSTNESS"
    assert intelligence.review.succeeded_count == 1


def test_synthesis_preserves_failure_and_scope_tension() -> None:
    intelligence = synthesize_research_brain(_view(failed_count=2, drift_warning_count=1))

    assert intelligence.rejected_or_failed_threads
    assert "2 failed experiment" in intelligence.rejected_or_failed_threads[0]
    assert intelligence.contradictions
    assert "focus boundary" in intelligence.contradictions[0]
