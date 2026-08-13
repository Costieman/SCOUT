"""Tests for end-to-end governed validation execution and persistence."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
)
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.validation_provenance import FileValidationReviewProvenanceStore
from trade_scout.validation.contracts import (
    DateInterval,
    SampleAccounting,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    WalkForwardFold,
)
from trade_scout.validation.evidence import EvidenceRole, EvidenceSnapshot, MetricEstimate
from trade_scout.validation.execution import (
    GovernedValidationWorkflow,
    ValidationExecutionContext,
    ValidationExecutionError,
    ValidationTargetResult,
    ValidationTargetType,
    execute_validation_design,
    materialize_validation_targets,
)
from trade_scout.validation.plan_store import FileRobustnessPlanStore, FileValidationPlanStore
from trade_scout.validation.robustness import RobustnessChallenge, RobustnessKind, RobustnessPlan
from trade_scout.validation.store import FileValidationReviewStore


def _plan() -> ValidationPlan:
    return ValidationPlan(
        plan_id="validation-v1",
        segments=(
            ValidationSegment(
                "development",
                ValidationRole.DEVELOPMENT,
                DateInterval(date(2018, 1, 1), date(2019, 12, 31)),
            ),
            ValidationSegment(
                "validation",
                ValidationRole.VALIDATION,
                DateInterval(date(2020, 1, 1), date(2021, 12, 31)),
            ),
            ValidationSegment(
                "holdout",
                ValidationRole.HOLDOUT,
                DateInterval(date(2024, 1, 1), date(2025, 12, 31)),
            ),
        ),
        walk_forward_folds=(
            WalkForwardFold(
                "wf-1",
                DateInterval(date(2018, 1, 1), date(2020, 12, 31)),
                DateInterval(date(2021, 1, 1), date(2021, 12, 31)),
            ),
            WalkForwardFold(
                "wf-2",
                DateInterval(date(2018, 1, 1), date(2021, 12, 31)),
                DateInterval(date(2022, 1, 1), date(2022, 12, 31)),
            ),
        ),
        primary_outcome="forward_return_60",
        robustness_checks=("entry-shift", "cost-stress"),
    )


def _robustness_plan() -> RobustnessPlan:
    return RobustnessPlan(
        plan_id="robustness-v1",
        challenges=(
            RobustnessChallenge(
                "entry-shift",
                RobustnessKind.ENTRY_SHIFT,
                "Shift entry by one session.",
                ("entry_convention",),
            ),
            RobustnessChallenge(
                "cost-stress",
                RobustnessKind.COST_STRESS,
                "Increase transaction costs.",
                ("costs",),
            ),
        ),
    )


def _manifest(status: ExperimentStatus = ExperimentStatus.SUCCEEDED) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="experiment-001",
        definition=ExperimentDefinition(
            name="confirmatory breakout",
            hypothesis="The frozen rule changes forward return.",
            mode=ResearchMode.CONFIRMATORY,
            dataset_version="dataset-v1",
            universe_version="universe-v1",
            code_version="abc123",
            config_schema_version="1",
            resolved_configuration={"horizon": 60},
        ),
        status=status,
        created_at="2026-08-13T00:00:00Z",
        completed_at="2026-08-13T01:00:00Z" if status is ExperimentStatus.SUCCEEDED else None,
    )


class _SyntheticExecutor:
    def __init__(self, *, wrong_target: str | None = None) -> None:
        self.contexts: list[ValidationExecutionContext] = []
        self.wrong_target = wrong_target

    def execute_validation_target(
        self,
        context: ValidationExecutionContext,
    ) -> ValidationTargetResult:
        self.contexts.append(context)
        target = context.target
        role = target.evidence_role
        fold_id = (
            target.target_id
            if target.target_type is ValidationTargetType.WALK_FORWARD_FOLD
            else None
        )
        challenge_id = (
            target.target_id
            if target.target_type is ValidationTargetType.ROBUSTNESS_CHALLENGE
            else None
        )
        if self.wrong_target == target.target_id:
            role = EvidenceRole.DEVELOPMENT
        return ValidationTargetResult(
            EvidenceSnapshot(
                evidence_id=f"evidence-{target.target_id}",
                role=role,
                sample=SampleAccounting(raw_event_count=50, unique_instrument_count=30),
                metrics=(MetricEstimate(context.primary_outcome, 0.01, "fraction"),),
                fold_id=fold_id,
                challenge_id=challenge_id,
            )
        )


def _stores(
    tmp_path: Path,
) -> tuple[
    FileValidationPlanStore,
    FileRobustnessPlanStore,
    FileManifestStore,
    FileValidationReviewStore,
    FileValidationReviewProvenanceStore,
]:
    validation_store = FileValidationPlanStore(tmp_path / "designs")
    robustness_store = FileRobustnessPlanStore(tmp_path / "designs")
    manifest_store = FileManifestStore(tmp_path / "experiments")
    review_store = FileValidationReviewStore(tmp_path / "reviews")
    provenance_store = FileValidationReviewProvenanceStore(tmp_path / "provenance")
    return validation_store, robustness_store, manifest_store, review_store, provenance_store


def test_materializes_all_frozen_targets_in_deterministic_order() -> None:
    targets = materialize_validation_targets(_plan(), _robustness_plan())

    assert [(target.target_type, target.target_id) for target in targets] == [
        (ValidationTargetType.SEGMENT, "development"),
        (ValidationTargetType.SEGMENT, "validation"),
        (ValidationTargetType.SEGMENT, "holdout"),
        (ValidationTargetType.WALK_FORWARD_FOLD, "wf-1"),
        (ValidationTargetType.WALK_FORWARD_FOLD, "wf-2"),
        (ValidationTargetType.ROBUSTNESS_CHALLENGE, "entry-shift"),
        (ValidationTargetType.ROBUSTNESS_CHALLENGE, "cost-stress"),
    ]
    assert targets[0].interval == DateInterval(date(2018, 1, 1), date(2019, 12, 31))
    assert targets[3].development_interval == DateInterval(date(2018, 1, 1), date(2020, 12, 31))
    assert targets[-1].changed_fields == ("costs",)


def test_executes_every_target_and_assembles_complete_review() -> None:
    executor = _SyntheticExecutor()

    bundle = execute_validation_design(
        experiment_id="experiment-001",
        plan=_plan(),
        executor=executor,
        report_id="review-001",
        robustness_plan=_robustness_plan(),
    )

    assert bundle.completeness.complete
    assert len(bundle.assignments) == 7
    assert len(bundle.report.snapshots) == 7
    assert bundle.robustness_plan_id == "robustness-v1"
    assert [context.target.target_id for context in executor.contexts] == [
        "development",
        "validation",
        "holdout",
        "wf-1",
        "wf-2",
        "entry-shift",
        "cost-stress",
    ]


def test_target_role_mismatch_fails_before_review_assembly() -> None:
    executor = _SyntheticExecutor(wrong_target="holdout")

    with pytest.raises(ValidationExecutionError, match="returned role"):
        execute_validation_design(
            experiment_id="experiment-001",
            plan=_plan(),
            executor=executor,
            report_id="review-001",
            robustness_plan=_robustness_plan(),
        )


def test_workflow_persists_review_and_provenance_from_frozen_sources(tmp_path: Path) -> None:
    validation_store, robustness_store, manifest_store, review_store, provenance_store = _stores(
        tmp_path
    )
    validation_store.write(_plan())
    robustness_store.write(_robustness_plan())
    manifest_store.write_manifest(_manifest())
    executor = _SyntheticExecutor()
    workflow = GovernedValidationWorkflow(
        validation_plan_store=validation_store,
        robustness_plan_store=robustness_store,
        experiment_manifest_reader=manifest_store,
        review_store=review_store,
        provenance_store=provenance_store,
        executor=executor,
    )

    receipt = workflow.run(
        experiment_id="experiment-001",
        validation_plan_id="validation-v1",
        robustness_plan_id="robustness-v1",
        report_id="review-001",
    )

    assert receipt.target_count == 7
    assert receipt.review_checksum == review_store.checksum("review-001")
    assert receipt.provenance_checksum == provenance_store.checksum("review-001")
    assert review_store.read("review-001").completeness.complete
    provenance = provenance_store.read("review-001")
    assert provenance.validation_plan_id == "validation-v1"
    assert provenance.robustness_plan_id == "robustness-v1"
    assert provenance.experiment_id == "experiment-001"


def test_workflow_refuses_unsucceeded_source_experiment(tmp_path: Path) -> None:
    validation_store, robustness_store, manifest_store, review_store, provenance_store = _stores(
        tmp_path
    )
    validation_store.write(_plan())
    robustness_store.write(_robustness_plan())
    manifest_store.write_manifest(_manifest(ExperimentStatus.FAILED))
    workflow = GovernedValidationWorkflow(
        validation_plan_store=validation_store,
        robustness_plan_store=robustness_store,
        experiment_manifest_reader=manifest_store,
        review_store=review_store,
        provenance_store=provenance_store,
        executor=_SyntheticExecutor(),
    )

    with pytest.raises(ValidationExecutionError, match="must be SUCCEEDED"):
        workflow.run(
            experiment_id="experiment-001",
            validation_plan_id="validation-v1",
            robustness_plan_id="robustness-v1",
            report_id="review-001",
        )

    assert not (tmp_path / "reviews" / "review-001.json").exists()


def test_workflow_requires_exact_frozen_robustness_declaration(tmp_path: Path) -> None:
    validation_store, robustness_store, manifest_store, review_store, provenance_store = _stores(
        tmp_path
    )
    changed = RobustnessPlan(
        plan_id="robustness-v1",
        challenges=tuple(reversed(_robustness_plan().challenges)),
    )
    validation_store.write(_plan())
    robustness_store.write(changed)
    manifest_store.write_manifest(_manifest())
    workflow = GovernedValidationWorkflow(
        validation_plan_store=validation_store,
        robustness_plan_store=robustness_store,
        experiment_manifest_reader=manifest_store,
        review_store=review_store,
        provenance_store=provenance_store,
        executor=_SyntheticExecutor(),
    )

    with pytest.raises(ValidationExecutionError, match="do not exactly match"):
        workflow.run(
            experiment_id="experiment-001",
            validation_plan_id="validation-v1",
            robustness_plan_id="robustness-v1",
            report_id="review-001",
        )
