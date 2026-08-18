from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from trade_scout.app.research_brain_checkpoints import FileResearchBrainCheckpointStore
from trade_scout.app.research_brain_http import handle_research_brain_post
from trade_scout.app.research_brain_review import build_research_brain_review
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_brain_surface import render_research_brains_html
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _SweepStage:
    name = "strategy_builder_entry_sweep"

    def __init__(self, expectancy: float) -> None:
        self._expectancy = expectancy

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={
                "points": [
                    {
                        "value": 10.0,
                        "complete_event_count": 25,
                        "expectancy_return": 0.01,
                    },
                    {
                        "value": 20.0,
                        "complete_event_count": 12,
                        "expectancy_return": self._expectancy,
                    },
                ]
            },
        )


def _definition(name: str) -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        hypothesis="Does one local parameter region deserve a controlled follow-up?",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="dataset-v1",
        universe_version="reviewed_canonical",
        code_version="code-v1",
        config_schema_version="strategy-builder-experiment-v0.1",
        resolved_configuration={
            "surface": "visual_strategy_builder",
            "entry": {"family": "feature_expression", "expression": "return_20 > 0"},
            "outcome": {"maximum_holding_period_sessions": 20},
            "research_variable": {
                "kind": "entry_parameter_sweep",
                "label": "Historical Volatility period",
                "declared_values": [10.0, 20.0],
            },
        },
    )


def _seed(tmp_path: Path) -> tuple[ResearchBrainWorkbenchService, str]:
    experiment_root = tmp_path / "research" / "experiments"
    store = FileManifestStore(experiment_root)
    first = ExperimentRunner(store, id_factory=lambda: "exp_first").run(
        _definition("First sweep"),
        (_SweepStage(0.08),),
    )
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=tmp_path / "research" / "brains",
    )
    brain = service.create_brain(
        brain_id="brain_checkpoint_test",
        name="Checkpoint test",
        research_question="How does this evidence change as we add controlled experiments?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=first.experiment_id,
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 1, tzinfo=UTC),
    )
    return service, brain.brain_id


def test_checkpoint_freezes_exact_review_and_membership_state(tmp_path: Path) -> None:
    service, brain_id = _seed(tmp_path)

    checkpoint = service.save_review_checkpoint(
        brain_id=brain_id,
        created_by="local-user",
        note="Before adding the second experiment.",
        created_at=datetime(2026, 8, 18, 8, 2, tzinfo=UTC),
    )
    current = service.detail(brain_id)

    assert checkpoint.brain_id == brain_id
    assert checkpoint.review.readiness_label == "DESCRIPTIVE_REVIEW_AVAILABLE"
    assert [item.experiment_id for item in checkpoint.memberships] == ["exp_first"]
    assert current.review_checkpoints == (checkpoint,)
    assert current.review_checkpoints[0].note == "Before adding the second experiment."


def test_checkpoint_becomes_historical_when_brain_membership_changes(tmp_path: Path) -> None:
    service, brain_id = _seed(tmp_path)
    checkpoint = service.save_review_checkpoint(
        brain_id=brain_id,
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 8, 2, tzinfo=UTC),
    )
    checkpoint_store = FileResearchBrainCheckpointStore(service.brain_root)
    before = service.detail(brain_id)
    assert checkpoint_store.verify_current_membership_state(checkpoint, before) is True

    experiment_store = FileManifestStore(tmp_path / "research" / "experiments")
    second = ExperimentRunner(experiment_store, id_factory=lambda: "exp_second").run(
        _definition("Second sweep"),
        (_SweepStage(0.03),),
    )
    service.add_experiment(
        brain_id=brain_id,
        experiment_id=second.experiment_id,
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 3, tzinfo=UTC),
    )
    after = service.detail(brain_id)

    assert checkpoint_store.verify_current_membership_state(checkpoint, after) is False
    assert [item.experiment_id for item in checkpoint.memberships] == ["exp_first"]
    assert [item.experiment_id for item in after.snapshot.memberships] == [
        "exp_first",
        "exp_second",
    ]


def test_checkpoint_round_trip_preserves_review_payload(tmp_path: Path) -> None:
    service, brain_id = _seed(tmp_path)
    view = service.detail(brain_id)
    review = build_research_brain_review(view.snapshot, view.experiments)
    store = FileResearchBrainCheckpointStore(service.brain_root)

    created = store.create(
        view,
        review,
        created_by="local-user",
        note="Round-trip fixture",
        created_at=datetime(2026, 8, 18, 8, 4, tzinfo=UTC),
        checkpoint_id="brainreview_fixture",
    )
    loaded = store.read(brain_id, "brainreview_fixture")

    assert loaded == created
    assert loaded.review.findings == review.findings
    assert loaded.review.sweep_observations == review.sweep_observations


def test_checkpoint_post_is_explicit_and_surface_lists_history(tmp_path: Path) -> None:
    service, brain_id = _seed(tmp_path)
    recorder = StrategyBuilderExperimentRecorder(
        experiment_root=tmp_path / "research" / "experiments",
        dataset_version="dataset-v1",
        code_version="code-v1",
    )
    body = (
        f"action=checkpoint&brain_id={brain_id}&actor=local-user&note=First+descriptive+review"
    ).encode()

    status, location = handle_research_brain_post(body, recorder)

    assert status is HTTPStatus.SEE_OTHER
    parameters = parse_qs(urlsplit(location).query)
    assert parameters["brain"] == [brain_id]
    assert "Saved brain review checkpoint" in parameters["message"][0]
    detail = service.detail(brain_id)
    html = render_research_brains_html(brains=service.list_brains(), detail=detail)
    assert "Save review checkpoint" in html
    assert "Saved review checkpoints" in html
    assert "First descriptive review" in html
    assert "does not rerun research, choose winners, or validate anything" in html


def test_rendering_brain_review_does_not_create_checkpoint(tmp_path: Path) -> None:
    service, brain_id = _seed(tmp_path)
    before = service.detail(brain_id)
    assert before.review_checkpoints == ()

    html = render_research_brains_html(brains=service.list_brains(), detail=before)

    assert "No review checkpoints saved yet" in html
    assert service.detail(brain_id).review_checkpoints == ()
