from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from trade_scout.app.research_brain_conditioning import (
    ConditioningState,
    build_research_brain_conditioning,
)
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_brain_surface import render_research_brains_html
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _ExploratorySweepStage:
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
                ],
                "out_of_sample_status": "NOT_RUN",
                "multiplicity_status": "NOT_RUN",
            },
        )


class _ControlledSweepStage:
    name = "strategy_builder_entry_sweep"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={
                "points": [
                    {
                        "value": 10.0,
                        "complete_event_count": 120,
                        "expectancy_return": 0.012,
                    },
                    {
                        "value": 15.0,
                        "complete_event_count": 110,
                        "expectancy_return": 0.018,
                    },
                    {
                        "value": 20.0,
                        "complete_event_count": 100,
                        "expectancy_return": 0.020,
                    },
                ],
                "comparator_excess_return": 0.004,
                "confidence_interval": [0.001, 0.007],
                "adjusted_p_value": 0.03,
                "holdout_result": {"expectancy_return": 0.006},
                "walk_forward_folds": [
                    {"fold": 1, "expectancy_return": 0.004},
                    {"fold": 2, "expectancy_return": 0.007},
                ],
            },
        )


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


def _service(tmp_path: Path, stage: object) -> ResearchBrainWorkbenchService:
    experiment_root = tmp_path / "research" / "experiments"
    store = FileManifestStore(experiment_root)
    ExperimentRunner(store, id_factory=lambda: "exp_sweep").run(
        _definition("Historical volatility period sweep"),
        (stage,),
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
    return service


def test_conditioning_maps_missing_controls_without_creating_a_score(tmp_path: Path) -> None:
    service = _service(tmp_path, _ExploratorySweepStage())
    view = service.detail("brain_volatility")

    conditioning = build_research_brain_conditioning(view)

    assert conditioning.version == "research-brain-conditioning-v0.1"
    assert not hasattr(conditioning, "score")
    assert conditioning.dimension("integrity").state is ConditioningState.AVAILABLE
    assert conditioning.dimension("sample_support").state is ConditioningState.PARTIAL
    assert conditioning.dimension("comparator").state is ConditioningState.MISSING
    assert conditioning.dimension("uncertainty").state is ConditioningState.MISSING
    assert conditioning.dimension("parameter_stability").state is ConditioningState.AVAILABLE
    assert conditioning.dimension("out_of_sample").state is ConditioningState.MISSING
    assert conditioning.dimension("time_stability").state is ConditioningState.MISSING
    assert conditioning.dimension("search_burden").state is ConditioningState.PARTIAL
    assert conditioning.priority_key == "comparator"
    assert "baseline/control" in conditioning.priority_action


def test_conditioning_shows_neighbor_values_and_exact_search_burden(tmp_path: Path) -> None:
    service = _service(tmp_path, _ExploratorySweepStage())
    conditioning = build_research_brain_conditioning(service.detail("brain_volatility"))

    stability = conditioning.dimension("parameter_stability")
    search = conditioning.dimension("search_burden")

    assert any("historical peak 20 at +12.48%" in item for item in stability.evidence)
    assert any("left neighbor 15 at +3.20%" in item for item in stability.evidence)
    assert any("right neighbor 25 at +11.79%" in item for item in stability.evidence)
    assert "5 readable tested sweep cell(s)" in search.summary
    assert "no explicit multiplicity" in search.summary


def test_explicit_control_uncertainty_oos_time_and_multiplicity_fields_are_detected(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, _ControlledSweepStage())
    conditioning = build_research_brain_conditioning(service.detail("brain_volatility"))

    assert conditioning.dimension("comparator").state is ConditioningState.AVAILABLE
    assert conditioning.dimension("uncertainty").state is ConditioningState.AVAILABLE
    assert conditioning.dimension("out_of_sample").state is ConditioningState.AVAILABLE
    assert conditioning.dimension("time_stability").state is ConditioningState.AVAILABLE
    assert conditioning.dimension("search_burden").state is ConditioningState.AVAILABLE
    assert conditioning.priority_key is None
    assert "Do not tune further" in conditioning.priority_action


def test_surface_explains_conditioning_in_plain_language(tmp_path: Path) -> None:
    service = _service(tmp_path, _ExploratorySweepStage())
    view = service.detail("brain_volatility")

    html = render_research_brains_html(
        brains=service.list_brains(),
        detail=view,
    )

    assert "Brain conditioning — evidence quality map" in html
    assert "No overall score" in html
    assert "Comparison evidence" in html
    assert "Not found / not tested" in html
    assert "Sample support" in html
    assert "N=2 to N=28" in html
    assert "Search burden" in html
    assert "Next evidence priority: Comparison evidence" in html
    assert "does not validate a strategy" in html


def test_empty_brain_conditions_to_add_evidence_first(tmp_path: Path) -> None:
    experiment_root = tmp_path / "research" / "experiments"
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=tmp_path / "research" / "brains",
    )
    service.create_brain(
        brain_id="brain_empty",
        name="Empty brain",
        research_question="What belongs here?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )

    conditioning = build_research_brain_conditioning(service.detail("brain_empty"))

    assert conditioning.dimension("integrity").state is ConditioningState.MISSING
    assert conditioning.priority_key == "integrity"
    assert conditioning.priority_title == "First add evidence"
