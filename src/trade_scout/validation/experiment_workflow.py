"""Experiment Runner-backed governed validation with mandatory child provenance.

This workflow requires every frozen validation target to execute as a durable child experiment.
Success is returned only after the review, review provenance, and ordered child-experiment provenance
are persisted and independently re-verifiable.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.experiments.validation_child_provenance import (
    FileValidationChildProvenanceStore,
    build_validation_child_provenance,
    verify_validation_child_provenance,
)
from trade_scout.experiments.validation_provenance import FileValidationReviewProvenanceStore
from trade_scout.validation.execution import (
    ExperimentManifestReader,
    GovernedValidationWorkflow,
    ValidationExecutionContext,
    ValidationExecutionError,
    ValidationExecutionReceipt,
    ValidationTargetResult,
    materialize_validation_targets,
)
from trade_scout.validation.parameter_surface import ParameterSurface
from trade_scout.validation.plan_store import FileRobustnessPlanStore, FileValidationPlanStore
from trade_scout.validation.reporting import MultiplicitySummary
from trade_scout.validation.runner_adapter import (
    ExperimentRunnerValidationTargetExecutor,
    ValidationTargetExperimentExecution,
)
from trade_scout.validation.store import FileValidationReviewStore


@dataclass(frozen=True, slots=True)
class ExperimentRunnerValidationReceipt:
    """Durable identities emitted only after mandatory child lineage is persisted."""

    validation: ValidationExecutionReceipt
    child_provenance_checksum: str
    child_experiment_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.child_provenance_checksum) != 64 or any(
            character not in "0123456789abcdef" for character in self.child_provenance_checksum
        ):
            raise ValueError("child_provenance_checksum must be a lowercase SHA-256 digest")
        if len(self.child_experiment_ids) != self.validation.target_count:
            raise ValueError("child experiment count must equal validation target count")
        if len(self.child_experiment_ids) != len(set(self.child_experiment_ids)):
            raise ValueError("child experiment IDs must be unique")


class _CapturingExperimentExecutor:
    def __init__(self, executor: ExperimentRunnerValidationTargetExecutor) -> None:
        self._executor = executor
        self.executions: list[ValidationTargetExperimentExecution] = []

    def execute_validation_target(
        self,
        context: ValidationExecutionContext,
    ) -> ValidationTargetResult:
        execution = self._executor.execute_validation_target_with_manifest(context)
        self.executions.append(execution)
        return execution.result


class ExperimentRunnerGovernedValidationWorkflow:
    """Run governed validation and require child-experiment provenance before success."""

    def __init__(
        self,
        *,
        validation_plan_store: FileValidationPlanStore,
        robustness_plan_store: FileRobustnessPlanStore,
        experiment_manifest_reader: ExperimentManifestReader,
        review_store: FileValidationReviewStore,
        provenance_store: FileValidationReviewProvenanceStore,
        child_provenance_store: FileValidationChildProvenanceStore,
        executor: ExperimentRunnerValidationTargetExecutor,
    ) -> None:
        self._validation_plan_store = validation_plan_store
        self._robustness_plan_store = robustness_plan_store
        self._experiment_manifest_reader = experiment_manifest_reader
        self._review_store = review_store
        self._provenance_store = provenance_store
        self._child_provenance_store = child_provenance_store
        self._executor = executor

    def run(
        self,
        *,
        experiment_id: str,
        validation_plan_id: str,
        report_id: str,
        robustness_plan_id: str | None = None,
        parameter_surfaces: tuple[ParameterSurface, ...] = (),
        multiplicity: tuple[MultiplicitySummary, ...] = (),
        report_notes: tuple[str, ...] = (),
    ) -> ExperimentRunnerValidationReceipt:
        """Execute all targets and persist review plus both provenance layers."""

        try:
            plan = self._validation_plan_store.read_validation_plan(validation_plan_id)
            robustness_plan = (
                self._robustness_plan_store.read_robustness_plan(robustness_plan_id)
                if robustness_plan_id is not None
                else None
            )
            expected_targets = materialize_validation_targets(plan, robustness_plan)
        except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed to resolve validation targets for child provenance: {exc}"
            ) from exc

        capturing = _CapturingExperimentExecutor(self._executor)
        base = GovernedValidationWorkflow(
            validation_plan_store=self._validation_plan_store,
            robustness_plan_store=self._robustness_plan_store,
            experiment_manifest_reader=self._experiment_manifest_reader,
            review_store=self._review_store,
            provenance_store=self._provenance_store,
            executor=capturing,
        )
        receipt = base.run(
            experiment_id=experiment_id,
            validation_plan_id=validation_plan_id,
            report_id=report_id,
            robustness_plan_id=robustness_plan_id,
            parameter_surfaces=parameter_surfaces,
            multiplicity=multiplicity,
            report_notes=report_notes,
        )

        child_manifests = tuple(execution.child_manifest for execution in capturing.executions)
        expected_target_ids = tuple(target.target_id for target in expected_targets)
        if len(child_manifests) != receipt.target_count:
            raise ValidationExecutionError(
                "validation completed without exactly one durable child manifest per target"
            )

        try:
            child_provenance = build_validation_child_provenance(
                report_id=report_id,
                validation_plan_id=validation_plan_id,
                source_experiment_id=experiment_id,
                review_provenance_checksum=receipt.provenance_checksum,
                child_manifests=child_manifests,
                expected_target_ids=expected_target_ids,
            )
            child_checksum = self._child_provenance_store.write(child_provenance)
            verify_validation_child_provenance(
                self._child_provenance_store.read(report_id),
                manifest_reader=self._experiment_manifest_reader,
                current_review_provenance_checksum=receipt.provenance_checksum,
            )
        except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed mandatory validation child provenance for {report_id}: {exc}"
            ) from exc

        return ExperimentRunnerValidationReceipt(
            validation=receipt,
            child_provenance_checksum=child_checksum,
            child_experiment_ids=tuple(manifest.experiment_id for manifest in child_manifests),
        )
