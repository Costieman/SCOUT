from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.app.research_brain_review import build_research_brain_review
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_brain_surface import render_research_brains_html
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _SweepStage:
    name = "strategy_builder_entry_sweep"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={
                "points": [
                    {
                        "value": 10.0,
                        "complete_event_count": 28,
                        "expectancy_return": 0.0093,
                    },
                    {
                        "value": 15.0,
                        "complete_event_count": 18,
                        "expectancy_return": 0.032,
                    },
                    {
                        "value": 20.0,
                        "complete_event_count": 10,
                        "expectancy_return": 0.1248,
                    },
                    {
                        "value": 25.0,
                        "complete_event_count": 8,
                        "expectancy_return": 0.1179,
                    },
                    {
                        "value": 30.0,
                        "complete_event_count": 2,
                        "expectancy_return": -0.0834,
                    },
                ]
            },
        )


class _FailingStage:
    name = "strategy_builder"

    def run(self, context: ExperimentContext) -> StageResult:
        raise RuntimeError("synthetic failure retained as research history")


def _definition(name: str) -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        hypothesis="Does volatility lookback change the outcome distribution?",
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
                "target_feature_name": "historical_volatility",
                "parameter": "period",
                "declared_values": [10.0, 15.0, 20.0, 25.0, 30.0],
            },
        },
    )


def _service(tmp_path: Path) -> ResearchBrainWorkbenchService:
    experiment_root = tmp_path / "research" / "experiments"
    store = FileManifestStore(experiment_root)
    ExperimentRunner(store, id_factory=lambda: "exp_sweep").run(
        _definition("Historical volatility period sweep"),
        (_SweepStage(),),
    )
    with pytest.raises(ExperimentExecutionError):
        ExperimentRunner(store, id_factory=lambda: "exp_failed").run(
            _definition("Failed follow-up"),
            (_FailingStage(),),
        )
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=tmp_path / "research" / "brains",
    )
    brain = service.create_brain(
        brain_id="brain_volatility",
        name="Volatility research",
        research_question="Which volatility settings deserve a more controlled follow-up?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id="exp_sweep",
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 1, tzinfo=UTC),
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id="exp_failed",
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 2, tzinfo=UTC),
    )
    return service


def test_review_reports_observed_peak_without_calling_it_an_optimum(tmp_path: Path) -> None:
    service = _service(tmp_path)
    detail = service.detail("brain_volatility")

    review = build_research_brain_review(detail.snapshot, detail.experiments)

    assert review.readiness_label == "DESCRIPTIVE_REVIEW_AVAILABLE"
    assert review.sweep_count == 1
    assert review.failed_count == 1
    sweep = review.sweep_observations[0]
    assert sweep.variable_label == "Historical Volatility period"
    assert sweep.best_observed_value == 20.0
    assert sweep.best_observed_expectancy == pytest.approx(0.1248)
    assert sweep.best_observed_complete_events == 10
    assert sweep.smallest_complete_events == 2
    assert sweep.largest_complete_events == 28
    assert any("not a validated optimum" in item for item in review.findings)
    assert any("N ranges from 2 to 28" in item for item in review.cautions)
    assert any("failed experiment" in item for item in review.cautions)


def test_review_surface_uses_plain_language_and_keeps_validation_boundary(tmp_path: Path) -> None:
    service = _service(tmp_path)
    detail = service.detail("brain_volatility")

    html = render_research_brains_html(
        brains=service.list_brains(),
        detail=detail,
    )

    assert "Brain review — what the saved evidence currently says" in html
    assert "Structured descriptive review available" in html
    assert "Historical Volatility period" in html
    assert "+12.48%" in html
    assert "N=10 complete events" in html
    assert "complete-event N ranges from 2 to 28" in html
    assert "not a validated optimum" in html
    assert "not validation, optimization, or a trading recommendation" in html
    assert "appropriate comparator" in html


def test_empty_brain_does_not_use_magic_run_count(tmp_path: Path) -> None:
    experiment_root = tmp_path / "research" / "experiments"
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=tmp_path / "research" / "brains",
    )
    service.create_brain(
        brain_id="brain_empty",
        name="Empty brain",
        research_question="What should we learn here?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    detail = service.detail("brain_empty")

    review = build_research_brain_review(detail.snapshot, detail.experiments)

    assert review.readiness_label == "EMPTY"
    assert "not a fixed run count" in review.readiness_explanation
    assert review.next_questions == (
        "Attach the first relevant experiment to establish the brain's evidence history.",
    )
