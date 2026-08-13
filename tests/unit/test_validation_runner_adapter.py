"""Tests for governed validation targets executed through the real Experiment Runner."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.validation.contracts import DateInterval, SampleAccounting, ValidationRole
from trade_scout.validation.evidence import EvidenceRole, EvidenceSnapshot, MetricEstimate
from trade_scout.validation.execution import (
    ValidationExecutionContext,
    ValidationExecutionError,
    ValidationTarget,
    ValidationTargetType,
)
from trade_scout.validation.runner_adapter import (
    ExperimentRunnerValidationTargetExecutor,
    ValidationTargetExperimentSpec,
)


class _Stage:
    name = "estimate"

    def run(self, context: ExperimentContext) -> StageResult:
        target = context.definition.resolved_configuration.get("_validation_target", {})
        target_id = target.get("target_id") if isinstance(target, dict) else "source"
        return StageResult(
            self.name,
            {
                "estimate": 0.012,
                "raw_event_count": 40,
                "unique_instrument_count": 25,
                "target_id": str(target_id),
            },
        )


class _Factory:
    def __init__(self, definition: ExperimentDefinition | None = None) -> None:
        self.definition = definition
        self.contexts: list[ValidationExecutionContext] = []

    def build_validation_experiment(
        self,
        context: ValidationExecutionContext,
        source_manifest: ExperimentManifest,
    ) -> ValidationTargetExperimentSpec:
        self.contexts.append(context)
        definition = self.definition or replace(
            source_manifest.definition,
            name=f"validation {context.target.target_id}",
            hypothesis=f"Evaluate frozen target {context.target.target_id}.",
            parent_experiment_id=None,
            resolved_configuration={"analysis": "fixed"},
        )
        return ValidationTargetExperimentSpec(definition, (_Stage(),))


class _Extractor:
    def __init__(self, *, wrong_role: bool = False) -> None:
        self.wrong_role = wrong_role
        self.child_ids: list[str] = []

    def extract_validation_evidence(
        self,
        context: ValidationExecutionContext,
        manifest: ExperimentManifest,
        artifacts: tuple[tuple[str, dict[str, Any]], ...],
    ) -> EvidenceSnapshot:
        self.child_ids.append(manifest.experiment_id)
        stage_name, output = artifacts[0]
        assert stage_name == "estimate"
        assert output["target_id"] == context.target.target_id
        role = EvidenceRole.DEVELOPMENT if self.wrong_role else context.target.evidence_role
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
            role=role,
            sample=SampleAccounting(
                raw_event_count=int(output["raw_event_count"]),
                unique_instrument_count=int(output["unique_instrument_count"]),
            ),
            metrics=(MetricEstimate(context.primary_outcome, float(output["estimate"]), "fraction"),),
            fold_id=fold_id,
            challenge_id=challenge_id,
        )


def _definition(**changes: Any) -> ExperimentDefinition:
    base = ExperimentDefinition(
        name="source research",
        hypothesis="Frozen research definition.",
        mode=ResearchMode.CONFIRMATORY,
        dataset_version="dataset-v1",
        universe_version="universe-v1",
        code_version="code-v1",
        config_schema_version="1",
        resolved_configuration={"window": 20},
    )
    return replace(base, **changes)


def _source(store: FileManifestStore) -> str:
    runner = ExperimentRunner(store, id_factory=lambda: "source-exp")
    manifest = runner.run(_definition(), (_Stage(),))
    assert manifest.status is ExperimentStatus.SUCCEEDED
    return manifest.experiment_id


def _segment_context(source_id: str) -> ValidationExecutionContext:
    return ValidationExecutionContext(
        experiment_id=source_id,
        validation_plan_id="plan-v1",
        primary_outcome="forward_return_60",
        target=ValidationTarget(
            ValidationTargetType.SEGMENT,
            "validation",
            EvidenceRole.VALIDATION,
            segment_role=ValidationRole.VALIDATION,
            interval=DateInterval(date(2020, 1, 1), date(2021, 12, 31)),
        ),
    )


def _executor(
    store: FileManifestStore,
    *,
    factory: _Factory | None = None,
    extractor: _Extractor | None = None,
) -> ExperimentRunnerValidationTargetExecutor:
    return ExperimentRunnerValidationTargetExecutor(
        runner=ExperimentRunner(store, id_factory=lambda: "validation-child-001"),
        artifact_reader=store,
        factory=factory or _Factory(),
        extractor=extractor or _Extractor(),
    )


def test_executes_target_through_real_runner_and_reads_persisted_output(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    source_id = _source(store)
    factory = _Factory()
    extractor = _Extractor()

    result = _executor(store, factory=factory, extractor=extractor).execute_validation_target(
        _segment_context(source_id)
    )

    assert result.snapshot.metrics[0].estimate == pytest.approx(0.012)
    assert result.snapshot.sample.raw_event_count == 40
    child = store.read_manifest("validation-child-001")
    assert child.status is ExperimentStatus.SUCCEEDED
    assert child.definition.parent_experiment_id == source_id
    metadata = child.definition.resolved_configuration["_validation_target"]
    assert isinstance(metadata, dict)
    assert metadata["target_id"] == "validation"
    assert metadata["validation_plan_id"] == "plan-v1"
    assert store.read_stage_output(child.experiment_id, "estimate")["estimate"] == 0.012
    assert extractor.child_ids == ["validation-child-001"]
    assert len(factory.contexts) == 1


def test_rejects_undeclared_dataset_drift_before_child_execution(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    source_id = _source(store)
    changed = _definition(
        dataset_version="dataset-v2",
        parent_experiment_id=source_id,
        resolved_configuration={"analysis": "fixed"},
    )

    with pytest.raises(ValidationExecutionError, match="outside DATASET_REVISION"):
        _executor(store, factory=_Factory(changed)).execute_validation_target(
            _segment_context(source_id)
        )


def test_dataset_revision_challenge_may_use_explicit_new_dataset(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    source_id = _source(store)
    context = ValidationExecutionContext(
        experiment_id=source_id,
        validation_plan_id="plan-v1",
        primary_outcome="forward_return_60",
        target=ValidationTarget(
            ValidationTargetType.ROBUSTNESS_CHALLENGE,
            "corrected-dataset",
            EvidenceRole.ROBUSTNESS,
            robustness_kind="DATASET_REVISION",
            robustness_description="Rerun against a corrected immutable dataset.",
            changed_fields=("data.dataset_version",),
        ),
    )
    changed = _definition(
        dataset_version="dataset-v2",
        parent_experiment_id=source_id,
        resolved_configuration={"analysis": "fixed"},
    )

    result = _executor(store, factory=_Factory(changed)).execute_validation_target(context)

    assert result.snapshot.challenge_id == "corrected-dataset"
    assert store.read_manifest("validation-child-001").definition.dataset_version == "dataset-v2"


def test_rejects_reserved_target_metadata_collision(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    source_id = _source(store)
    proposed = _definition(
        parent_experiment_id=source_id,
        resolved_configuration={"_validation_target": {"fake": True}},
    )

    with pytest.raises(ValidationExecutionError, match="reserved key"):
        _executor(store, factory=_Factory(proposed)).execute_validation_target(
            _segment_context(source_id)
        )


def test_rejects_production_monitoring_or_conflicting_parent(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    source_id = _source(store)
    production = _definition(
        mode=ResearchMode.PRODUCTION_MONITORING,
        parent_experiment_id=source_id,
        resolved_configuration={"analysis": "fixed"},
    )
    with pytest.raises(ValidationExecutionError, match="PRODUCTION_MONITORING"):
        _executor(store, factory=_Factory(production)).execute_validation_target(
            _segment_context(source_id)
        )

    conflicting = _definition(
        parent_experiment_id="other-exp",
        resolved_configuration={"analysis": "fixed"},
    )
    with pytest.raises(ValidationExecutionError, match="conflicting parent"):
        _executor(store, factory=_Factory(conflicting)).execute_validation_target(
            _segment_context(source_id)
        )


def test_extractor_cannot_return_wrong_evidence_role(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    source_id = _source(store)

    with pytest.raises(ValidationExecutionError, match="evidence role mismatch"):
        _executor(store, extractor=_Extractor(wrong_role=True)).execute_validation_target(
            _segment_context(source_id)
        )
