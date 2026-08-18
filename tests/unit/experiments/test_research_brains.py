from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.research_brains import (
    BrainAlignmentState,
    BrainFocusRule,
    FileResearchBrainStore,
    ResearchBrainDefinition,
    ResearchBrainError,
    assess_brain_alignment,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _Stage:
    name = "research"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(stage_name=self.name, outputs={"mean_return": 0.01})


class _FailingStage:
    name = "research"

    def run(self, context: ExperimentContext) -> StageResult:
        raise RuntimeError("negative knowledge fixture")


def _definition(*, family: str, expression: str = "return_20 > 0") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=f"{family} research",
        hypothesis="Test one research condition without promotion.",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="brain-dataset-v1",
        universe_version="reviewed_canonical",
        code_version="brain-code-v1",
        config_schema_version="brain-test-v1",
        resolved_configuration={
            "surface": "visual_strategy_builder",
            "entry": {"family": family, "expression": expression},
            "outcome": {"maximum_holding_period_sessions": 20},
        },
    )


def _successful_manifest(root: Path, *, experiment_id: str, family: str) -> ExperimentManifest:
    return ExperimentRunner(
        FileManifestStore(root),
        id_factory=lambda: experiment_id,
    ).run(_definition(family=family), (_Stage(),))


def _failed_manifest(root: Path, *, experiment_id: str, family: str) -> ExperimentManifest:
    store = FileManifestStore(root)
    runner = ExperimentRunner(store, id_factory=lambda: experiment_id)
    with pytest.raises(ExperimentExecutionError):
        runner.run(_definition(family=family), (_FailingStage(),))
    return store.read_manifest(experiment_id)


def _brain(*, with_focus: bool = True) -> ResearchBrainDefinition:
    rules = (
        (
            BrainFocusRule(
                configuration_path="entry.family",
                allowed_values=("feature_expression",),
                rationale="This brain studies feature-expression entry questions.",
            ),
        )
        if with_focus
        else ()
    )
    return ResearchBrainDefinition(
        brain_id="brain_entry_context",
        name="Entry context brain",
        research_question="Which related entry conditions add useful information?",
        created_by="researcher",
        created_at=datetime(2026, 8, 18, 7, 0, tzinfo=UTC).isoformat(),
        focus_rules=rules,
    )


def test_brain_definition_is_checksum_verified_and_immutable(tmp_path: Path) -> None:
    store = FileResearchBrainStore(tmp_path / "brains")
    definition = _brain()

    checksum = store.create(definition)

    assert len(checksum) == 64
    assert store.read_definition(definition.brain_id) == definition
    with pytest.raises(ResearchBrainError, match="already exists"):
        store.create(definition)


def test_brain_preserves_success_and_failure_memberships(tmp_path: Path) -> None:
    experiment_root = tmp_path / "experiments"
    succeeded = _successful_manifest(
        experiment_root,
        experiment_id="exp_success",
        family="feature_expression",
    )
    failed = _failed_manifest(
        experiment_root,
        experiment_id="exp_failed",
        family="feature_expression",
    )
    store = FileResearchBrainStore(tmp_path / "brains")
    store.create(_brain())

    first = store.add_experiment("brain_entry_context", succeeded, added_by="researcher")
    second = store.add_experiment("brain_entry_context", failed, added_by="researcher")
    snapshot = store.snapshot("brain_entry_context")

    assert first.alignment_state is BrainAlignmentState.IN_SCOPE
    assert second.alignment_state is BrainAlignmentState.IN_SCOPE
    assert [item.experiment_id for item in snapshot.memberships] == ["exp_success", "exp_failed"]
    assert snapshot.succeeded_count == 1
    assert snapshot.failed_count == 1
    assert snapshot.conditioning_readiness == "NOT_ASSESSED"
    assert "not inferred from a fixed run-count threshold" in snapshot.conditioning_note


def test_scope_drift_warns_but_does_not_block_or_delete_experiment(tmp_path: Path) -> None:
    manifest = _successful_manifest(
        tmp_path / "experiments",
        experiment_id="exp_breakout",
        family="consolidation_breakout",
    )
    store = FileResearchBrainStore(tmp_path / "brains")
    store.create(_brain())

    membership = store.add_experiment(
        "brain_entry_context",
        manifest,
        added_by="researcher",
        note="Deliberate boundary challenge.",
    )
    snapshot = store.snapshot("brain_entry_context")

    assert membership.alignment_state is BrainAlignmentState.DRIFT_WARNING
    assert "entry.family='consolidation_breakout'" in membership.alignment_reasons[0]
    assert snapshot.drift_warning_count == 1
    assert [item.experiment_id for item in snapshot.memberships] == ["exp_breakout"]


def test_brain_without_explicit_focus_rules_is_unassessed_not_falsely_in_scope(
    tmp_path: Path,
) -> None:
    manifest = _successful_manifest(
        tmp_path / "experiments",
        experiment_id="exp_unassessed",
        family="feature_expression",
    )
    definition = _brain(with_focus=False)

    alignment, reasons = assess_brain_alignment(definition, manifest)

    assert alignment is BrainAlignmentState.UNASSESSED
    assert reasons == ()


def test_duplicate_experiment_membership_is_rejected_without_rewriting_history(
    tmp_path: Path,
) -> None:
    manifest = _successful_manifest(
        tmp_path / "experiments",
        experiment_id="exp_once",
        family="feature_expression",
    )
    store = FileResearchBrainStore(tmp_path / "brains")
    store.create(_brain())
    first = store.add_experiment("brain_entry_context", manifest, added_by="researcher")

    with pytest.raises(ResearchBrainError, match="already belongs"):
        store.add_experiment("brain_entry_context", manifest, added_by="researcher")

    assert store.memberships("brain_entry_context") == (first,)


def test_membership_binds_exact_experiment_manifest_checksum(tmp_path: Path) -> None:
    manifest = _successful_manifest(
        tmp_path / "experiments",
        experiment_id="exp_bound",
        family="feature_expression",
    )
    store = FileResearchBrainStore(tmp_path / "brains")
    store.create(_brain())
    membership = store.add_experiment("brain_entry_context", manifest, added_by="researcher")

    assert store.verify_membership_experiment("brain_entry_context", manifest) == membership

    changed = replace(manifest, manifest_checksum="0" * 64)
    with pytest.raises(ResearchBrainError, match="changed after brain membership"):
        store.verify_membership_experiment("brain_entry_context", changed)


def test_non_terminal_experiment_cannot_enter_brain(tmp_path: Path) -> None:
    succeeded = _successful_manifest(
        tmp_path / "experiments",
        experiment_id="exp_terminal",
        family="feature_expression",
    )
    running = replace(succeeded, status=ExperimentStatus.RUNNING)
    store = FileResearchBrainStore(tmp_path / "brains")
    store.create(_brain())

    with pytest.raises(ResearchBrainError, match="terminal"):
        store.add_experiment("brain_entry_context", running, added_by="researcher")


def test_membership_rejects_naive_timestamp(tmp_path: Path) -> None:
    manifest = _successful_manifest(
        tmp_path / "experiments",
        experiment_id="exp_naive_time",
        family="feature_expression",
    )
    store = FileResearchBrainStore(tmp_path / "brains")
    store.create(_brain())

    with pytest.raises(ValueError, match="timezone-aware"):
        store.add_experiment(
            "brain_entry_context",
            manifest,
            added_by="researcher",
            added_at=datetime(2026, 8, 18, 7, 0),
        )
