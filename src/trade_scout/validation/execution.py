"""End-to-end orchestration for governed statistical validation.

The workflow materializes every target declared by an immutable validation design, delegates the
actual analytical calculation to an injected executor, verifies exact target/evidence identity,
assembles the complete review bundle, persists the review, and cryptographically binds that review
to the frozen design and source experiment manifest. It deliberately does not interpret the
statistical evidence or assign a research-decision state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from trade_scout.experiments.contracts import ExperimentManifest, ExperimentStatus
from trade_scout.experiments.validation_provenance import (
    FileValidationReviewProvenanceStore,
    build_validation_review_provenance,
)
from trade_scout.validation.completeness import EvidenceAssignment, EvidenceTargetKind
from trade_scout.validation.contracts import (
    DateInterval,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    WalkForwardFold,
)
from trade_scout.validation.evidence import EvidenceRole, EvidenceSnapshot, ValidationEvidenceReport
from trade_scout.validation.parameter_surface import ParameterSurface
from trade_scout.validation.plan_store import FileRobustnessPlanStore, FileValidationPlanStore
from trade_scout.validation.reporting import (
    MultiplicitySummary,
    ValidationReviewBundle,
    assemble_validation_review_bundle,
)
from trade_scout.validation.robustness import RobustnessChallenge, RobustnessPlan
from trade_scout.validation.store import FileValidationReviewStore


class ValidationExecutionError(RuntimeError):
    """Raised when a governed validation workflow cannot be completed reproducibly."""


class ValidationTargetType(StrEnum):
    """Canonical executable target families derived from a frozen validation design."""

    SEGMENT = "SEGMENT"
    WALK_FORWARD_FOLD = "WALK_FORWARD_FOLD"
    ROBUSTNESS_CHALLENGE = "ROBUSTNESS_CHALLENGE"


@dataclass(frozen=True, slots=True)
class ValidationTarget:
    """One immutable analytical target to be executed exactly once."""

    target_type: ValidationTargetType
    target_id: str
    evidence_role: EvidenceRole
    segment_role: ValidationRole | None = None
    interval: DateInterval | None = None
    development_interval: DateInterval | None = None
    validation_interval: DateInterval | None = None
    robustness_kind: str | None = None
    robustness_description: str | None = None
    changed_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.target_id.strip():
            raise ValueError("validation target_id must be non-empty")
        if self.target_type is ValidationTargetType.SEGMENT:
            if self.segment_role is None or self.interval is None:
                raise ValueError("segment targets require segment_role and interval")
            if self.development_interval is not None or self.validation_interval is not None:
                raise ValueError("segment targets cannot carry walk-forward intervals")
            if self.robustness_kind is not None or self.robustness_description is not None:
                raise ValueError("segment targets cannot carry robustness metadata")
        elif self.target_type is ValidationTargetType.WALK_FORWARD_FOLD:
            if self.development_interval is None or self.validation_interval is None:
                raise ValueError("walk-forward targets require development and validation intervals")
            if self.evidence_role is not EvidenceRole.WALK_FORWARD:
                raise ValueError("walk-forward targets require WALK_FORWARD evidence role")
            if self.segment_role is not None or self.interval is not None:
                raise ValueError("walk-forward targets cannot carry segment metadata")
        elif self.target_type is ValidationTargetType.ROBUSTNESS_CHALLENGE:
            if not self.robustness_kind or not self.robustness_description:
                raise ValueError("robustness targets require kind and description")
            if self.evidence_role is not EvidenceRole.ROBUSTNESS:
                raise ValueError("robustness targets require ROBUSTNESS evidence role")
            if not self.changed_fields:
                raise ValueError("robustness targets require changed_fields")


@dataclass(frozen=True, slots=True)
class ValidationExecutionContext:
    """Frozen identities supplied to each analytical target execution."""

    experiment_id: str
    validation_plan_id: str
    primary_outcome: str
    target: ValidationTarget

    def __post_init__(self) -> None:
        for label, value in (
            ("experiment_id", self.experiment_id),
            ("validation_plan_id", self.validation_plan_id),
            ("primary_outcome", self.primary_outcome),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")


@dataclass(frozen=True, slots=True)
class ValidationTargetResult:
    """Evidence returned by one analytical target execution."""

    snapshot: EvidenceSnapshot


class ValidationTargetExecutor(Protocol):
    """Analytical adapter used by the governed workflow."""

    def execute_validation_target(
        self,
        context: ValidationExecutionContext,
    ) -> ValidationTargetResult: ...


class ExperimentManifestReader(Protocol):
    """Read one immutable checksum-verified experiment manifest."""

    def read_manifest(self, experiment_id: str) -> ExperimentManifest: ...


@dataclass(frozen=True, slots=True)
class ValidationExecutionReceipt:
    """Persistent identities produced by one completed governed validation workflow."""

    report_id: str
    experiment_id: str
    validation_plan_id: str
    robustness_plan_id: str | None
    target_count: int
    review_checksum: str
    provenance_checksum: str

    def __post_init__(self) -> None:
        if self.target_count <= 0:
            raise ValueError("target_count must be positive")
        for label, checksum in (
            ("review_checksum", self.review_checksum),
            ("provenance_checksum", self.provenance_checksum),
        ):
            if len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum
            ):
                raise ValueError(f"{label} must be a lowercase SHA-256 hexadecimal digest")


def materialize_validation_targets(
    plan: ValidationPlan,
    robustness_plan: RobustnessPlan | None = None,
) -> tuple[ValidationTarget, ...]:
    """Expand a frozen validation design into a deterministic executable target sequence."""

    targets: list[ValidationTarget] = []
    role_map = {
        ValidationRole.DEVELOPMENT: EvidenceRole.DEVELOPMENT,
        ValidationRole.VALIDATION: EvidenceRole.VALIDATION,
        ValidationRole.HOLDOUT: EvidenceRole.FINAL_HOLDOUT,
    }
    for segment in plan.segments:
        targets.append(_segment_target(segment, role_map[segment.role]))
    for fold in plan.walk_forward_folds:
        targets.append(_walk_forward_target(fold))
    if robustness_plan is not None:
        targets.extend(_robustness_target(challenge) for challenge in robustness_plan.challenges)

    identities = tuple((target.target_type, target.target_id) for target in targets)
    if len(identities) != len(set(identities)):
        raise ValidationExecutionError("materialized validation target identities are not unique")
    return tuple(targets)


def execute_validation_design(
    *,
    experiment_id: str,
    plan: ValidationPlan,
    executor: ValidationTargetExecutor,
    report_id: str,
    robustness_plan: RobustnessPlan | None = None,
    parameter_surfaces: tuple[ParameterSurface, ...] = (),
    multiplicity: tuple[MultiplicitySummary, ...] = (),
    report_notes: tuple[str, ...] = (),
) -> ValidationReviewBundle:
    """Execute every frozen target and assemble an exactly complete review bundle."""

    if not report_id.strip():
        raise ValueError("report_id must be non-empty")
    primary_outcome = plan.primary_outcome
    if primary_outcome is None or not primary_outcome.strip():
        raise ValidationExecutionError(
            "governed validation execution requires the frozen plan to declare primary_outcome"
        )
    targets = materialize_validation_targets(plan, robustness_plan)
    if not targets:
        raise ValidationExecutionError("frozen validation design materialized no targets")

    snapshots: list[EvidenceSnapshot] = []
    assignments: list[EvidenceAssignment] = []
    seen_evidence_ids: set[str] = set()
    for target in targets:
        context = ValidationExecutionContext(
            experiment_id=experiment_id,
            validation_plan_id=plan.plan_id,
            primary_outcome=primary_outcome,
            target=target,
        )
        result = executor.execute_validation_target(context)
        snapshot = result.snapshot
        _require_target_snapshot_identity(target, snapshot)
        if snapshot.evidence_id in seen_evidence_ids:
            raise ValidationExecutionError(
                f"duplicate evidence_id returned by target executor: {snapshot.evidence_id}"
            )
        seen_evidence_ids.add(snapshot.evidence_id)
        snapshots.append(snapshot)
        assignments.append(_assignment_for(target, snapshot.evidence_id))

    if len(multiplicity) > 1:
        raise ValidationExecutionError(
            "one validation report can declare at most one multiplicity family"
        )
    report = ValidationEvidenceReport(
        report_id=report_id,
        experiment_id=experiment_id,
        validation_plan_id=plan.plan_id,
        primary_outcome=primary_outcome,
        snapshots=tuple(snapshots),
        multiplicity_family_id=(multiplicity[0].family.family_id if multiplicity else None),
        notes=report_notes,
    )
    return assemble_validation_review_bundle(
        plan=plan,
        report=report,
        assignments=tuple(assignments),
        robustness_plan=robustness_plan,
        parameter_surfaces=parameter_surfaces,
        multiplicity=multiplicity,
    )


class GovernedValidationWorkflow:
    """Resolve frozen sources, execute validation, persist review, and bind provenance."""

    def __init__(
        self,
        *,
        validation_plan_store: FileValidationPlanStore,
        robustness_plan_store: FileRobustnessPlanStore,
        experiment_manifest_reader: ExperimentManifestReader,
        review_store: FileValidationReviewStore,
        provenance_store: FileValidationReviewProvenanceStore,
        executor: ValidationTargetExecutor,
    ) -> None:
        self._validation_plan_store = validation_plan_store
        self._robustness_plan_store = robustness_plan_store
        self._experiment_manifest_reader = experiment_manifest_reader
        self._review_store = review_store
        self._provenance_store = provenance_store
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
    ) -> ValidationExecutionReceipt:
        """Run the complete governed workflow without making a scientific promotion decision."""

        try:
            plan = self._validation_plan_store.read_validation_plan(validation_plan_id)
            robustness_plan = (
                self._robustness_plan_store.read_robustness_plan(robustness_plan_id)
                if robustness_plan_id is not None
                else None
            )
            manifest = self._experiment_manifest_reader.read_manifest(experiment_id)
        except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed to resolve frozen validation sources: {exc}"
            ) from exc

        _require_manifest_ready(manifest, experiment_id)
        _require_robustness_declaration(plan, robustness_plan)

        bundle = execute_validation_design(
            experiment_id=experiment_id,
            plan=plan,
            executor=self._executor,
            report_id=report_id,
            robustness_plan=robustness_plan,
            parameter_surfaces=parameter_surfaces,
            multiplicity=multiplicity,
            report_notes=report_notes,
        )
        try:
            review_checksum = self._review_store.write(bundle)
            provenance = build_validation_review_provenance(
                bundle=bundle,
                review_checksum=review_checksum,
                plan=plan,
                experiment_manifest=manifest,
                robustness_plan=robustness_plan,
            )
            provenance_checksum = self._provenance_store.write(provenance)
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ValidationExecutionError(
                f"failed to persist governed validation evidence: {exc}"
            ) from exc

        return ValidationExecutionReceipt(
            report_id=report_id,
            experiment_id=experiment_id,
            validation_plan_id=validation_plan_id,
            robustness_plan_id=robustness_plan_id,
            target_count=len(bundle.assignments),
            review_checksum=review_checksum,
            provenance_checksum=provenance_checksum,
        )


def _segment_target(segment: ValidationSegment, evidence_role: EvidenceRole) -> ValidationTarget:
    return ValidationTarget(
        target_type=ValidationTargetType.SEGMENT,
        target_id=segment.segment_id,
        evidence_role=evidence_role,
        segment_role=segment.role,
        interval=segment.interval,
    )


def _walk_forward_target(fold: WalkForwardFold) -> ValidationTarget:
    return ValidationTarget(
        target_type=ValidationTargetType.WALK_FORWARD_FOLD,
        target_id=fold.fold_id,
        evidence_role=EvidenceRole.WALK_FORWARD,
        development_interval=fold.development,
        validation_interval=fold.validation,
    )


def _robustness_target(challenge: RobustnessChallenge) -> ValidationTarget:
    return ValidationTarget(
        target_type=ValidationTargetType.ROBUSTNESS_CHALLENGE,
        target_id=challenge.challenge_id,
        evidence_role=EvidenceRole.ROBUSTNESS,
        robustness_kind=challenge.kind.value,
        robustness_description=challenge.description,
        changed_fields=challenge.changed_fields,
    )


def _assignment_for(target: ValidationTarget, evidence_id: str) -> EvidenceAssignment:
    kind_map = {
        ValidationTargetType.SEGMENT: EvidenceTargetKind.SEGMENT,
        ValidationTargetType.WALK_FORWARD_FOLD: EvidenceTargetKind.WALK_FORWARD_FOLD,
        ValidationTargetType.ROBUSTNESS_CHALLENGE: EvidenceTargetKind.ROBUSTNESS_CHALLENGE,
    }
    return EvidenceAssignment(evidence_id, kind_map[target.target_type], target.target_id)


def _require_target_snapshot_identity(target: ValidationTarget, snapshot: EvidenceSnapshot) -> None:
    if snapshot.role is not target.evidence_role:
        raise ValidationExecutionError(
            f"target {target.target_id!r} returned role {snapshot.role.value}, "
            f"expected {target.evidence_role.value}"
        )
    if target.target_type is ValidationTargetType.WALK_FORWARD_FOLD:
        if snapshot.fold_id != target.target_id:
            raise ValidationExecutionError(
                f"walk-forward target {target.target_id!r} returned mismatched fold_id"
            )
    elif snapshot.fold_id is not None:
        raise ValidationExecutionError(
            f"non-walk-forward target {target.target_id!r} returned fold_id"
        )
    if target.target_type is ValidationTargetType.ROBUSTNESS_CHALLENGE:
        if snapshot.challenge_id != target.target_id:
            raise ValidationExecutionError(
                f"robustness target {target.target_id!r} returned mismatched challenge_id"
            )
    elif snapshot.challenge_id is not None:
        raise ValidationExecutionError(
            f"non-robustness target {target.target_id!r} returned challenge_id"
        )


def _require_manifest_ready(manifest: ExperimentManifest, experiment_id: str) -> None:
    if manifest.experiment_id != experiment_id:
        raise ValidationExecutionError(
            f"source experiment identity mismatch: expected {experiment_id}, got {manifest.experiment_id}"
        )
    if manifest.status is not ExperimentStatus.SUCCEEDED:
        raise ValidationExecutionError(
            f"source experiment must be SUCCEEDED before validation: {manifest.status.value}"
        )
    if manifest.manifest_checksum is None:
        raise ValidationExecutionError("source experiment manifest has no checksum")


def _require_robustness_declaration(
    plan: ValidationPlan,
    robustness_plan: RobustnessPlan | None,
) -> None:
    declared = tuple(plan.robustness_checks)
    if robustness_plan is None:
        if declared:
            raise ValidationExecutionError(
                "validation plan declares robustness checks but no frozen robustness plan was supplied"
            )
        return
    challenge_ids = tuple(challenge.challenge_id for challenge in robustness_plan.challenges)
    if declared and declared != challenge_ids:
        raise ValidationExecutionError(
            "validation plan robustness_checks do not exactly match frozen robustness challenge order"
        )
