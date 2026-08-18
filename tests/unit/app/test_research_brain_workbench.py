from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from trade_scout.app.data_health_service import DataHealthSourcePaths
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_brain_http import (
    build_research_brains_page,
    handle_research_brain_post,
)
from trade_scout.app.research_brain_service import (
    ResearchBrainWorkbenchService,
    parse_focus_rules,
)
from trade_scout.app.research_workbench_console import (
    build_research_workbench_post_response,
    build_research_workbench_response,
)
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentStatus,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.research_brains import BrainAlignmentState
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _SweepStage:
    name = "strategy_builder_entry_sweep"

    def __init__(self, values: tuple[float, ...] = (10.0, 15.0, 20.0)) -> None:
        self._values = values

    def run(self, context: ExperimentContext) -> StageResult:
        points = [
            {
                "value": value,
                "complete_event_count": max(2, 40 - index * 10),
                "expectancy_return": 0.01 + index * 0.02,
            }
            for index, value in enumerate(self._values)
        ]
        return StageResult(stage_name=self.name, outputs={"points": points})


class _FailingStage:
    name = "strategy_builder"

    def run(self, context: ExperimentContext) -> StageResult:
        raise RuntimeError("synthetic research failure")


def _definition(
    name: str,
    *,
    family: str = "feature_expression",
) -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        hypothesis=f"Research question for {name}",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="dataset-v1",
        universe_version="reviewed_canonical",
        code_version="code-v1",
        config_schema_version="strategy-builder-experiment-v0.1",
        resolved_configuration={
            "surface": "visual_strategy_builder",
            "entry": {"family": family, "expression": "return_20 > 0"},
            "outcome": {"maximum_holding_period_sessions": 20},
        },
    )


def _seed_experiments(root: Path) -> tuple[str, str, str]:
    store = FileManifestStore(root)
    first = ExperimentRunner(store, id_factory=lambda: "exp_volatility").run(
        _definition("Historical volatility period sweep"),
        (_SweepStage(),),
    )
    second = ExperimentRunner(store, id_factory=lambda: "exp_breakout").run(
        _definition("Breakout boundary check", family="consolidation_breakout"),
        (_SweepStage((1.0, 2.0)),),
    )
    with pytest.raises(ExperimentExecutionError):
        ExperimentRunner(store, id_factory=lambda: "exp_failed").run(
            _definition("Failed volatility follow-up"),
            (_FailingStage(),),
        )
    return first.experiment_id, second.experiment_id, "exp_failed"


def _recorder(root: Path) -> StrategyBuilderExperimentRecorder:
    return StrategyBuilderExperimentRecorder(
        experiment_root=root,
        dataset_version="dataset-v1",
        code_version="code-v1",
    )


def _console_config(tmp_path: Path) -> LocalConsoleConfig:
    return LocalConsoleConfig(
        sources=DataHealthSourcePaths(
            tiingo_acceptance_path=tmp_path / "unused-tiingo.json",
            free_stack_acceptance_path=tmp_path / "unused-free-stack.json",
        )
    )


def test_brain_workbench_generates_id_preserves_failures_and_warns_on_drift(
    tmp_path: Path,
) -> None:
    experiment_root = tmp_path / "research" / "experiments"
    in_scope, drift, failed = _seed_experiments(experiment_root)
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=tmp_path / "research" / "brains",
    )

    brain = service.create_brain(
        name="Volatility in trend",
        research_question="Does volatility change the quality of trend entries?",
        created_by="local-user",
        focus_rules=parse_focus_rules("entry.family=feature_expression"),
        created_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )
    assert brain.brain_id.startswith("brain_volatility_in_trend_")

    first = service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=in_scope,
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 1, tzinfo=UTC),
    )
    second = service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=drift,
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 2, tzinfo=UTC),
    )
    third = service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=failed,
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 8, 3, tzinfo=UTC),
    )

    assert first.alignment_state is BrainAlignmentState.IN_SCOPE
    assert second.alignment_state is BrainAlignmentState.DRIFT_WARNING
    assert third.alignment_state is BrainAlignmentState.IN_SCOPE
    detail = service.detail(brain.brain_id)
    assert detail.snapshot.failed_count == 1
    assert detail.snapshot.drift_warning_count == 1
    assert all(item.integrity_error is None for item in detail.experiments)
    assert detail.experiments[-1].membership.experiment_status is ExperimentStatus.FAILED


def test_create_post_uses_plain_language_form_and_generated_id(tmp_path: Path) -> None:
    experiment_root = tmp_path / "research" / "experiments"
    recorder = _recorder(experiment_root)
    body = (
        b"action=create&name=Volatility+research&"
        b"research_question=Does+volatility+matter%3F&actor=local-user&notes=First+thread"
    )

    status, location = handle_research_brain_post(body, recorder)

    assert status is HTTPStatus.SEE_OTHER
    parameters = parse_qs(urlsplit(location).query)
    brain_id = parameters["brain"][0]
    assert brain_id.startswith("brain_volatility_research_")
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=experiment_root.parent / "brains",
    )
    assert service.detail(brain_id).snapshot.definition.name == "Volatility research"


def test_add_post_prefills_experiment_and_get_does_not_mutate(tmp_path: Path) -> None:
    experiment_root = tmp_path / "research" / "experiments"
    experiment_id, _, _ = _seed_experiments(experiment_root)
    recorder = _recorder(experiment_root)
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=experiment_root.parent / "brains",
    )
    brain = service.create_brain(
        name="Volatility map",
        research_question="What volatility region deserves another test?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
    )

    status, html = build_research_brains_page(f"experiment={experiment_id}", recorder)
    assert status is HTTPStatus.OK
    assert f'value="{experiment_id}"' in html
    assert "A brain is a saved research question" in html
    assert "Advanced: keep this brain tightly focused" in html
    assert service.detail(brain.brain_id).snapshot.memberships == ()

    body = (
        f"action=add&brain_id={brain.brain_id}&experiment_id={experiment_id}&"
        "actor=local-user&note=First+saved+sweep"
    ).encode()
    status, _ = handle_research_brain_post(body, recorder)
    assert status is HTTPStatus.SEE_OTHER
    assert [item.experiment_id for item in service.detail(brain.brain_id).snapshot.memberships] == [
        experiment_id
    ]


def test_console_exposes_brain_get_and_only_accepts_explicit_form_post(tmp_path: Path) -> None:
    experiment_root = tmp_path / "research" / "experiments"
    recorder = _recorder(experiment_root)
    config = _console_config(tmp_path)

    get_response = build_research_workbench_response(
        "/research/brains",
        config,
        experiment_recorder=recorder,
    )
    assert get_response.status_code == HTTPStatus.OK
    assert b"Research Brains" in get_response.body

    asset_response = build_research_workbench_response(
        "/assets/strategy-builder-research-memory.js",
        config,
        experiment_recorder=recorder,
    )
    assert asset_response.status_code == HTTPStatus.OK
    assert b"Add this run to a research brain" in asset_response.body
    assert b"break-inside: avoid-page" in asset_response.body

    wrong_type = build_research_workbench_post_response(
        "/research/brains",
        "application/json",
        b"{}",
        experiment_recorder=recorder,
    )
    assert wrong_type.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    unrelated = build_research_workbench_post_response(
        "/research/strategy",
        "application/x-www-form-urlencoded",
        b"action=create",
        experiment_recorder=recorder,
    )
    assert unrelated.status_code == HTTPStatus.METHOD_NOT_ALLOWED


def test_invalid_focus_boundary_returns_visible_bad_request(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path / "research" / "experiments")
    response = build_research_workbench_post_response(
        "/research/brains",
        "application/x-www-form-urlencoded",
        (
            b"action=create&name=Test&research_question=Question&actor=local-user&"
            b"focus_rules=not-an-equals-rule"
        ),
        experiment_recorder=recorder,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert b"Could not complete that action" in response.body
    assert b"PATH=VALUE" in response.body
