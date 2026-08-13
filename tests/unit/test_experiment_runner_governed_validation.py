"""Tests for Experiment Runner validation with mandatory child provenance."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from itertools import count
from pathlib import Path
from typing import Any

from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentManifest,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.validation_child_provenance import (
    FileValidationChildProvenanceStore,
    verify_validation_child_provenance,
)
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
from trade_scout.validation.execution import ValidationExecutionContext, ValidationTargetType
from trade_scout.validation.experiment_workflow import ExperimentRunnerGovernedValidationWorkflow
from trade_scout.validation.plan_store import FileRobustnessPlanStore, FileValidationPlanStore
from trade_scout.validation.robustness import RobustnessChallenge, RobustnessKind, RobustnessPlan
from trade_scout.validation.runner_adapter import (
    ExperimentRunnerValidationTargetExecutor,
    ValidationTargetExperimentSpec,
)
from trade_scout.validation.store import FileValidationReviewStore


class _Stage:
    name = "estimate"

    def run(self, context: ExperimentContext) -> StageResult:
        target = context.definition.resolved_configuration.get("_validation_target")
        target_id = "source"
        if isinstance(target, dict):
            target_id = str(target.get("target_id", "unknown"))
        return StageResult(
            self.name,
            {
                "estimate": 0.012,
                "raw_event_count": 40,
                "unique_instrument_count": 25,
                "target_id": target_id,
            },
        )


class _Factory:
    def build_validation_experiment(
        self,
        context: ValidationExecutionContext,
        source_manifest: ExperimentManifest,
    ) -> ValidationTargetExperimentSpec:
        definition = replace(
            source_manifest.definition,
            name=f"validation {context.target.target_id}",
            hypothesis=f"Evaluate frozen target {context.target.target_id}.",
            parent_experiment_id=None,
            resolved_configuration={"analysis": "fixed"},
        )
        return ValidationTargetExperimentSpec(definition, (_Stage(),))


class _Extractor:
    def extract_validation_evidence(
        self,
        context: ValidationExecutionContext,
        manifest: ExperimentManifest,
        artifacts: tuple[tuple[str, dict[str, Any]], ...],
    ) -> EvidenceSnapshot:
        stage_name, output = artifacts[0]
        assert stage_name == "estimate"
        assert output["target_id"] == context.target.target_id
        fold_id = (
            context.target.target_id
            if context.target.target_type is ValidationTargetType.WALK_FORWARD_FOLD
            else None
        )
        challenge_id = (
            context.target.target_id
            if context.target.target_type is ValidationTargetType.ROBUSTNESS_CHALLENGE
            else None
        )
        return EvidenceSnapshot(
            evidence_id=f"evidence-{manifest.experiment_id}",
            role=context.target.evidence_role,
            sample=SampleAccounting(
                raw_event_count=int(output["raw_event_count"]),
                unique_instrument_count=int(output["unique_instrument_count"]),
            ),
            metrics=(
                MetricEstimate(context.primary_outcome, float(output["estimate"]), "fraction"),
            ),
            fold_id=fold_id,
            challenge_id=challenge_id,
        )


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
        ),
        primary_outcome="forward_return_60",
        robustness_checks=("cost-stress",),
    )


def _robustness_plan() -> RobustnessPlan:
    return RobustnessPlan(
        plan_id="robustness-v1",
        challenges=(
            RobustnessChallenge(
                "cost-stress",
                RobustnessKind.COST_STRESS,
                "Increase transaction costs.",
                ("costs",),
            ),
        ),
    )


def _source_definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="source research",
        hypothesis="Frozen source research definition.",
        mode=ResearchMode.CONFIRMATORY,
        dataset_version="dataset-v1",
        universe_version="universe-v1",
        code_version="code-v1",
        config_schema_version="1",
        resolved_configuration={"window": 20},
    )


def _child_id_factory():
    sequence = count(1)

    def next_id() -> str:
        return f"validation-child-{next(sequence):03d}"

    return next_id


def test_runner_workflow_emits_mandatory_ordered_child_provenance(tmp_path: Path) -> None:
    validation_store = FileValidationPlanStore(tmp_path / "designs")
    robustness_store = FileRobustnessPlanStore(tmp_path / "designs")
    manifest_store = FileManifestStore(tmp_path / "experiments")
    review_store = FileValidationReviewStore(tmp_path / "reviews")
    provenance_store = FileValidationReviewProvenanceStore(tmp_path / "provenance")
    child_store = FileValidationChildProvenanceStore(tmp_path / "child-provenance")

    validation_store.write(_plan())
    robustness_store.write(_robustness_plan())
    source = ExperimentRunner(manifest_store, id_factory=lambda: "experiment-001").run(
        _source_definition(), (_Stage(),)
    )
    executor = ExperimentRunnerValidationTargetExecutor(
        runner=ExperimentRunner(manifest_store, id_factory=_child_id_factory()),
        artifact_reader=manifest_store,
        factory=_Factory(),
        extractor=_Extractor(),
    )
    workflow = ExperimentRunnerGovernedValidationWorkflow(
        validation_plan_store=validation_store,
        robustness_plan_store=robustness_store,
        experiment_manifest_reader=manifest_store,
        review_store=review_store,
        provenance_store=provenance_store,
        child_provenance_store=child_store,
        executor=executor,
    )

    receipt = workflow.run(
        experiment_id=source.experiment_id,
        validation_plan_id="validation-v1",
        robustness_plan_id="robustness-v1",
        report_id="review-001",
    )

    assert receipt.validation.target_count == 5
    assert receipt.validation.review_checksum == review_store.checksum("review-001")
    assert receipt.validation.provenance_checksum == provenance_store.checksum("review-001")
    assert receipt.child_provenance_checksum == child_store.checksum("review-001")
    assert receipt.child_experiment_ids == (
        "validation-child-001",
        "validation-child-002",
        "validation-child-003",
        "validation-child-004",
        "validation-child-005",
    )

    child_provenance = child_store.read("review-001")
    assert tuple(child.target_id for child in child_provenance.children) == (
        "development",
        "validation",
        "holdout",
        "wf-1",
        "cost-stress",
    )
    assert child_provenance.review_provenance_checksum == receipt.validation.provenance_checksum
    assert all(child.stage_artifacts for child in child_provenance.children)
    verify_validation_child_provenance(
        child_provenance,
        manifest_reader=manifest_store,
        current_review_provenance_checksum=receipt.validation.provenance_checksum,
    )
