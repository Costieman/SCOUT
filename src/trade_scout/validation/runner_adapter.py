"""Bridge governed validation targets to durable Experiment Runner child executions.

This adapter owns orchestration and lineage only. Target-specific analytical semantics remain in an
explicit factory, and evidence interpretation remains in an explicit extractor. In particular, the
adapter never guesses how a robustness challenge's ``changed_fields`` should mutate research
configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    JSONValue,
    ResearchMode,
    ResearchStage,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.validation.evidence import EvidenceSnapshot
from trade_scout.validation.execution import (
    ValidationExecutionContext,
    ValidationExecutionError,
    ValidationTargetResult,
    ValidationTargetType,
)

_VALIDATION_TARGET_CONFIG_KEY = "_validation_target"


@dataclass(frozen=True, slots=True)
class ValidationTargetExperimentSpec:
    """One child Experiment Runner request produced for a governed validation target."""

    definition: ExperimentDefinition
    stages: tuple[ResearchStage, ...]

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("validation target experiment must contain at least one stage")


@dataclass(frozen=True, slots=True)
class ValidationTargetExperimentExecution:
    """Evidence plus the exact durable child manifest that produced it."""

    result: ValidationTargetResult
    child_manifest: ExperimentManifest

    def __post_init__(self) -> None:
        if self.child_manifest.status is not ExperimentStatus.SUCCEEDED:
            raise ValueError("validation child execution manifest must be SUCCEEDED")
        if self.child_manifest.manifest_checksum is None:
            raise ValueError("validation child execution manifest must have a checksum")


class ValidationTargetExperimentFactory(Protocol):
    """Translate one governed target into explicit analytical Experiment Runner stages."""

    def build_validation_experiment(
        self,
        context: ValidationExecutionContext,
        source_manifest: ExperimentManifest,
    ) -> ValidationTargetExperimentSpec: ...


class ValidationExperimentArtifactReader(Protocol):
    """Read checksum-verified manifests and persisted child stage outputs."""

    def read_manifest(self, experiment_id: str) -> ExperimentManifest: ...

    def read_stage_output(
        self,
        experiment_id: str,
        stage_name: str,
    ) -> dict[str, JSONValue]: ...


class ValidationEvidenceExtractor(Protocol):
    """Convert one completed child experiment and its persisted artifacts into evidence."""

    def extract_validation_evidence(
        self,
        context: ValidationExecutionContext,
        manifest: ExperimentManifest,
        artifacts: tuple[tuple[str, dict[str, JSONValue]], ...],
    ) -> EvidenceSnapshot: ...


class ExperimentRunnerValidationTargetExecutor:
    """Execute each governed validation target through the real Experiment Runner.

    The factory is responsible for analytical meaning. This executor enforces source/child lineage,
    freezes target identity into reserved configuration metadata, runs the child experiment, rereads
    persisted stage outputs, and asks the extractor to construct the evidence snapshot.
    """

    def __init__(
        self,
        *,
        runner: ExperimentRunner,
        artifact_reader: ValidationExperimentArtifactReader,
        factory: ValidationTargetExperimentFactory,
        extractor: ValidationEvidenceExtractor,
    ) -> None:
        self._runner = runner
        self._artifact_reader = artifact_reader
        self._factory = factory
        self._extractor = extractor

    def execute_validation_target(
        self,
        context: ValidationExecutionContext,
    ) -> ValidationTargetResult:
        """Run one target as a durable child experiment and return persisted-derived evidence."""

        return self.execute_validation_target_with_manifest(context).result

    def execute_validation_target_with_manifest(
        self,
        context: ValidationExecutionContext,
    ) -> ValidationTargetExperimentExecution:
        """Run one target and expose the verified child manifest for provenance binding."""

        source = self._read_source(context.experiment_id)
        try:
            spec = self._factory.build_validation_experiment(context, source)
            definition = _govern_child_definition(context, source, spec.definition)
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed to build validation child experiment for {context.target.target_id}: {exc}"
            ) from exc

        try:
            child = self._runner.run(definition, spec.stages)
        except Exception as exc:
            raise ValidationExecutionError(
                f"validation child experiment failed for {context.target.target_id}: {exc}"
            ) from exc
        _require_child_manifest(child, context=context, source=source)

        try:
            artifacts = tuple(
                (
                    stage.stage_name,
                    self._artifact_reader.read_stage_output(child.experiment_id, stage.stage_name),
                )
                for stage in child.stages
            )
            snapshot = self._extractor.extract_validation_evidence(context, child, artifacts)
        except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed to extract validation evidence for {context.target.target_id}: {exc}"
            ) from exc

        _require_snapshot_identity(context, snapshot)
        return ValidationTargetExperimentExecution(ValidationTargetResult(snapshot), child)

    def _read_source(self, experiment_id: str) -> ExperimentManifest:
        try:
            manifest = self._artifact_reader.read_manifest(experiment_id)
        except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed to resolve source experiment {experiment_id}: {exc}"
            ) from exc
        if manifest.experiment_id != experiment_id:
            raise ValidationExecutionError(
                "source experiment identity mismatch: "
                f"expected {experiment_id}, got {manifest.experiment_id}"
            )
        if manifest.status is not ExperimentStatus.SUCCEEDED:
            raise ValidationExecutionError(
                f"source experiment must be SUCCEEDED: {manifest.status.value}"
            )
        if manifest.manifest_checksum is None:
            raise ValidationExecutionError("source experiment manifest has no checksum")
        return manifest


def _govern_child_definition(
    context: ValidationExecutionContext,
    source: ExperimentManifest,
    proposed: ExperimentDefinition,
) -> ExperimentDefinition:
    if proposed.mode is ResearchMode.PRODUCTION_MONITORING:
        raise ValueError("validation child experiments cannot use PRODUCTION_MONITORING mode")
    if proposed.mode is not source.definition.mode:
        raise ValueError("validation child experiment must preserve source research mode")
    if proposed.code_version != source.definition.code_version:
        raise ValueError("validation child experiment must preserve source code_version")
    if proposed.config_schema_version != source.definition.config_schema_version:
        raise ValueError("validation child experiment must preserve source config_schema_version")
    if proposed.parent_experiment_id not in (None, source.experiment_id):
        raise ValueError("validation child experiment has conflicting parent_experiment_id")

    target = context.target
    dataset_revision = (
        target.target_type is ValidationTargetType.ROBUSTNESS_CHALLENGE
        and target.robustness_kind == "DATASET_REVISION"
    )
    if proposed.dataset_version != source.definition.dataset_version and not dataset_revision:
        raise ValueError(
            "validation child dataset_version changed outside DATASET_REVISION challenge"
        )

    universe_changed = proposed.universe_version != source.definition.universe_version
    universe_declared = any(field.startswith("universe.") for field in target.changed_fields)
    if universe_changed and not universe_declared:
        raise ValueError(
            "validation child universe_version changed without declared universe field"
        )

    if _VALIDATION_TARGET_CONFIG_KEY in proposed.resolved_configuration:
        raise ValueError(
            f"resolved configuration uses reserved key {_VALIDATION_TARGET_CONFIG_KEY!r}"
        )
    configuration = dict(proposed.resolved_configuration)
    configuration[_VALIDATION_TARGET_CONFIG_KEY] = _target_metadata(context)
    return replace(
        proposed,
        parent_experiment_id=source.experiment_id,
        resolved_configuration=configuration,
    )


def _target_metadata(context: ValidationExecutionContext) -> dict[str, JSONValue]:
    target = context.target
    payload: dict[str, JSONValue] = {
        "validation_plan_id": context.validation_plan_id,
        "target_type": target.target_type.value,
        "target_id": target.target_id,
        "evidence_role": target.evidence_role.value,
        "primary_outcome": context.primary_outcome,
        "changed_fields": list(target.changed_fields),
    }
    if target.segment_role is not None:
        payload["segment_role"] = target.segment_role.value
    if target.interval is not None:
        payload["interval"] = {
            "start": target.interval.start.isoformat(),
            "end": target.interval.end.isoformat(),
        }
    if target.development_interval is not None:
        payload["development_interval"] = {
            "start": target.development_interval.start.isoformat(),
            "end": target.development_interval.end.isoformat(),
        }
    if target.validation_interval is not None:
        payload["validation_interval"] = {
            "start": target.validation_interval.start.isoformat(),
            "end": target.validation_interval.end.isoformat(),
        }
    if target.robustness_kind is not None:
        payload["robustness_kind"] = target.robustness_kind
    if target.robustness_description is not None:
        payload["robustness_description"] = target.robustness_description
    return payload


def _require_child_manifest(
    manifest: ExperimentManifest,
    *,
    context: ValidationExecutionContext,
    source: ExperimentManifest,
) -> None:
    if manifest.status is not ExperimentStatus.SUCCEEDED:
        raise ValidationExecutionError(
            f"validation child experiment did not succeed: {manifest.status.value}"
        )
    if manifest.manifest_checksum is None:
        raise ValidationExecutionError("validation child experiment manifest has no checksum")
    if manifest.definition.parent_experiment_id != source.experiment_id:
        raise ValidationExecutionError("validation child experiment lost source parent lineage")
    metadata = manifest.definition.resolved_configuration.get(_VALIDATION_TARGET_CONFIG_KEY)
    if metadata != _target_metadata(context):
        raise ValidationExecutionError("validation child experiment target metadata changed")


def _require_snapshot_identity(
    context: ValidationExecutionContext,
    snapshot: EvidenceSnapshot,
) -> None:
    target = context.target
    if snapshot.role is not target.evidence_role:
        raise ValidationExecutionError(
            f"validation evidence role mismatch for {target.target_id}: "
            f"{snapshot.role.value} != {target.evidence_role.value}"
        )
    expected_fold = (
        target.target_id if target.target_type is ValidationTargetType.WALK_FORWARD_FOLD else None
    )
    if snapshot.fold_id != expected_fold:
        raise ValidationExecutionError(
            f"validation evidence fold identity mismatch for {target.target_id}"
        )
    expected_challenge = (
        target.target_id
        if target.target_type is ValidationTargetType.ROBUSTNESS_CHALLENGE
        else None
    )
    if snapshot.challenge_id != expected_challenge:
        raise ValidationExecutionError(
            f"validation evidence challenge identity mismatch for {target.target_id}"
        )
