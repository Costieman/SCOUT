from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.app.research_brain_followups import (
    FollowUpKind,
    FollowUpReadiness,
    ResearchBrainFollowUpError,
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


class _PlainStage:
    name = "strategy_builder"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={
                "entry_event_count": 120,
                "complete_event_count": 100,
                "policies": [
                    {
                        "family": "hold_to_horizon",
                        "expectancy_return": 0.012,
                    }
                ],
            },
        )


class _ControlledSweepStage:
    name = "strategy_builder_entry_sweep"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={
                "comparator_effect": {"baseline": 0.004, "excess_vs_baseline": 0.003},
                "p_value": 0.08,
                "points": [
                    {"value": 15.0, "complete_event_count": 38, "expectancy_return": 0.025},
                    {"value": 20.0, "complete_event_count": 35, "expectancy_return": 0.03},
                ],
            },
        )


def _definition(name: str, *, sweep: bool = False) -> ExperimentDefinition:
    configuration: dict[str, object] = {
        "surface": "visual_strategy_builder",
        "entry": {"family": "feature_expression", "expression": "return_20 > 0"},
        "outcome": {"maximum_holding_period_sessions": 20},
    }
    if sweep:
        configuration["research_variable"] = {
            "kind": "entry_parameter_sweep",
            "label": "Historical Volatility period",
            "target_feature_name": "historical_volatility",
            "parameter": "period",
            "declared_values": [15.0, 20.0],
        }
    return ExperimentDefinition(
        name=name,
        hypothesis="Test a fixed research question without automatic promotion.",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="dataset-v1",
        universe_version="reviewed_canonical",
        code_version="code-v1",
        config_schema_version="strategy-builder-experiment-v0.1",
        resolved_configuration=configuration,  # type: ignore[arg-type]
    )


def _service(tmp_path: Path, *, sweep: bool = False) -> ResearchBrainWorkbenchService:
    experiment_root = tmp_path / "research" / "experiments"
    store = FileManifestStore(experiment_root)
    ExperimentRunner(store, id_factory=lambda: "exp_source").run(
        _definition("Source experiment", sweep=sweep),
        ((_ControlledSweepStage() if sweep else _PlainStage()),),
    )
    service = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=tmp_path / "research" / "brains",
    )
    brain = service.create_brain(
        brain_id="brain_followup",
        name="Follow-up brain",
        research_question="What should be challenged next?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id="exp_source",
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 10, 1, tzinfo=UTC),
    )
    return service


def test_draft_proposal_targets_conditioning_priority_without_running_research(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    experiment_root = tmp_path / "research" / "experiments"
    manifests_before = tuple(experiment_root.glob("*/manifest.json"))

    proposal = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )

    assert proposal.kind is FollowUpKind.COMPARATOR
    assert proposal.priority_key == "comparator"
    assert proposal.readiness is FollowUpReadiness.OPERATOR_INPUT_REQUIRED
    assert proposal.source_experiment_id == "exp_source"
    assert "predeclared comparator" in proposal.title.lower()
    assert proposal.required_operator_inputs
    assert "does not execute research" in proposal.execution_boundary.lower()
    assert tuple(experiment_root.glob("*/manifest.json")) == manifests_before


def test_approval_is_separate_and_still_does_not_create_an_experiment(tmp_path: Path) -> None:
    service = _service(tmp_path)
    experiment_root = tmp_path / "research" / "experiments"
    proposal = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )
    manifests_before = tuple(experiment_root.glob("*/manifest.json"))

    approval = service.approve_follow_up_proposal(
        brain_id="brain_followup",
        proposal_id=proposal.proposal_id,
        approved_by="local-user",
        note="Comparator is the right next challenge.",
        approved_at=datetime(2026, 8, 18, 10, 3, tzinfo=UTC),
    )
    detail = service.detail("brain_followup")

    assert approval.proposal_id == proposal.proposal_id
    assert len(detail.follow_up_proposals) == 1
    assert detail.follow_up_proposals[0].status == "APPROVED_NOT_RUN"
    assert tuple(experiment_root.glob("*/manifest.json")) == manifests_before


def test_repeated_draft_on_same_evidence_reuses_exact_proposal(tmp_path: Path) -> None:
    service = _service(tmp_path)

    first = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )
    second = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="another-user",
        created_at=datetime(2026, 8, 18, 10, 4, tzinfo=UTC),
    )

    assert second == first
    assert len(service.detail("brain_followup").follow_up_proposals) == 1


def test_brain_change_marks_old_proposal_stale_and_blocks_approval(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proposal = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )
    experiment_root = tmp_path / "research" / "experiments"
    ExperimentRunner(FileManifestStore(experiment_root), id_factory=lambda: "exp_new").run(
        _definition("New evidence"),
        (_PlainStage(),),
    )
    service.add_experiment(
        brain_id="brain_followup",
        experiment_id="exp_new",
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 10, 3, tzinfo=UTC),
    )

    detail = service.detail("brain_followup")

    assert detail.follow_up_proposals[0].status == "STALE"
    with pytest.raises(ResearchBrainFollowUpError, match="stale"):
        service.approve_follow_up_proposal(
            brain_id="brain_followup",
            proposal_id=proposal.proposal_id,
            approved_by="local-user",
        )


def test_parameter_stability_proposal_uses_existing_neighbor_values_not_new_search(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, sweep=True)

    proposal = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )

    assert proposal.kind is FollowUpKind.PARAMETER_STABILITY
    assert proposal.priority_key == "parameter_stability"
    assert proposal.readiness is FollowUpReadiness.READY_TO_PLAN
    assert "15" in proposal.proposed_change
    assert "20" in proposal.proposed_change
    assert "do not add a new wider search" in proposal.proposed_change.lower()


def test_surface_makes_draft_approval_and_execution_boundaries_obvious(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proposal = service.draft_follow_up_proposal(
        brain_id="brain_followup",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )
    detail = service.detail("brain_followup")

    html = render_research_brains_html(
        brains=service.list_brains(),
        detail=detail,
    )

    assert "Proposed next experiment — approval and execution gates" in html
    assert "Three separate steps" in html
    assert "Execution is another explicit click" in html
    assert proposal.proposal_id in html
    assert "Approve plan — do not run" in html
    assert "Draft — awaiting your approval" in html
    assert "does not execute research" in html
