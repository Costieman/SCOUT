"""Fail-closed completeness checks for governed validation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.validation.contracts import ValidationPlan, ValidationRole
from trade_scout.validation.evidence import EvidenceRole, ValidationEvidenceReport
from trade_scout.validation.robustness import RobustnessPlan


class EvidenceTargetKind(StrEnum):
    """Validation design object satisfied by one evidence snapshot."""

    SEGMENT = "SEGMENT"
    WALK_FORWARD_FOLD = "WALK_FORWARD_FOLD"
    ROBUSTNESS_CHALLENGE = "ROBUSTNESS_CHALLENGE"


@dataclass(frozen=True, slots=True)
class EvidenceAssignment:
    """Explicit link between one evidence snapshot and one predeclared validation target."""

    evidence_id: str
    target_kind: EvidenceTargetKind
    target_id: str

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must be non-empty")
        if not self.target_id.strip():
            raise ValueError("target_id must be non-empty")


@dataclass(frozen=True, slots=True)
class ValidationCompleteness:
    """Machine-readable coverage assessment for one validation evidence bundle."""

    complete: bool
    missing_targets: tuple[str, ...]
    unexpected_targets: tuple[str, ...]
    role_mismatches: tuple[str, ...]
    unassigned_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        issue_fields = (
            self.missing_targets,
            self.unexpected_targets,
            self.role_mismatches,
            self.unassigned_evidence,
        )
        if self.complete and any(issue_fields):
            raise ValueError("complete validation assessment cannot contain issues")
        if not self.complete and not any(issue_fields):
            raise ValueError("incomplete validation assessment must describe at least one issue")

    def require_complete(self) -> None:
        """Fail closed when any predeclared validation target lacks matching evidence."""

        if self.complete:
            return
        details = "; ".join(
            part
            for part in (
                _format_issue("missing", self.missing_targets),
                _format_issue("unexpected", self.unexpected_targets),
                _format_issue("role_mismatch", self.role_mismatches),
                _format_issue("unassigned", self.unassigned_evidence),
            )
            if part
        )
        raise IncompleteValidationEvidenceError(f"validation evidence is incomplete: {details}")


class IncompleteValidationEvidenceError(RuntimeError):
    """Raised when evidence does not cover the frozen validation design exactly."""


def assess_validation_completeness(
    *,
    plan: ValidationPlan,
    report: ValidationEvidenceReport,
    assignments: tuple[EvidenceAssignment, ...],
    robustness_plan: RobustnessPlan | None = None,
) -> ValidationCompleteness:
    """Verify exact evidence coverage without judging scientific success or failure."""

    if report.validation_plan_id != plan.plan_id:
        raise ValueError("evidence report validation_plan_id does not match validation plan")
    if plan.primary_outcome is not None and report.primary_outcome != plan.primary_outcome:
        raise ValueError("evidence report primary outcome does not match validation plan")

    snapshot_by_id = {snapshot.evidence_id: snapshot for snapshot in report.snapshots}
    if len(snapshot_by_id) != len(report.snapshots):
        raise ValueError("evidence report contains duplicate evidence IDs")

    assignment_ids = [assignment.evidence_id for assignment in assignments]
    if len(assignment_ids) != len(set(assignment_ids)):
        raise ValueError("one evidence snapshot cannot satisfy multiple validation targets")

    expected_roles = _expected_targets(plan=plan, robustness_plan=robustness_plan)
    expected_keys = set(expected_roles)
    observed_keys: set[tuple[EvidenceTargetKind, str]] = set()
    role_mismatches: list[str] = []
    unexpected_targets: list[str] = []

    for assignment in assignments:
        key = (assignment.target_kind, assignment.target_id)
        if key in observed_keys:
            raise ValueError("validation target cannot receive multiple evidence assignments")
        observed_keys.add(key)
        snapshot = snapshot_by_id.get(assignment.evidence_id)
        if snapshot is None:
            unexpected_targets.append(
                _target_label(assignment.target_kind, assignment.target_id)
                + f"->unknown_evidence:{assignment.evidence_id}"
            )
            continue
        expected_role = expected_roles.get(key)
        if expected_role is None:
            unexpected_targets.append(_target_label(*key))
            continue
        if snapshot.role is not expected_role:
            role_mismatches.append(
                f"{assignment.evidence_id}:{snapshot.role.value}!={expected_role.value}"
            )
        _validate_intrinsic_identity(snapshot, assignment)

    missing = sorted(_target_label(*key) for key in expected_keys - observed_keys)
    unexpected = tuple(sorted(unexpected_targets))
    mismatches = tuple(sorted(role_mismatches))
    assigned_snapshot_ids = set(assignment_ids)
    unassigned = tuple(sorted(set(snapshot_by_id) - assigned_snapshot_ids))
    complete = not missing and not unexpected and not mismatches and not unassigned
    return ValidationCompleteness(
        complete=complete,
        missing_targets=tuple(missing),
        unexpected_targets=unexpected,
        role_mismatches=mismatches,
        unassigned_evidence=unassigned,
    )


def _expected_targets(
    *,
    plan: ValidationPlan,
    robustness_plan: RobustnessPlan | None,
) -> dict[tuple[EvidenceTargetKind, str], EvidenceRole]:
    result: dict[tuple[EvidenceTargetKind, str], EvidenceRole] = {}
    segment_roles = {
        ValidationRole.DEVELOPMENT: EvidenceRole.DEVELOPMENT,
        ValidationRole.VALIDATION: EvidenceRole.VALIDATION,
        ValidationRole.HOLDOUT: EvidenceRole.FINAL_HOLDOUT,
    }
    for segment in plan.segments:
        result[(EvidenceTargetKind.SEGMENT, segment.segment_id)] = segment_roles[segment.role]
    for fold in plan.walk_forward_folds:
        result[(EvidenceTargetKind.WALK_FORWARD_FOLD, fold.fold_id)] = EvidenceRole.WALK_FORWARD
    if robustness_plan is not None:
        for challenge in robustness_plan.challenges:
            result[(EvidenceTargetKind.ROBUSTNESS_CHALLENGE, challenge.challenge_id)] = (
                EvidenceRole.ROBUSTNESS
            )
    return result


def _validate_intrinsic_identity(snapshot: object, assignment: EvidenceAssignment) -> None:
    from trade_scout.validation.evidence import EvidenceSnapshot

    if not isinstance(snapshot, EvidenceSnapshot):
        raise TypeError("validation report contains an unsupported evidence snapshot")
    if (
        assignment.target_kind is EvidenceTargetKind.WALK_FORWARD_FOLD
        and snapshot.fold_id != assignment.target_id
    ):
        raise ValueError("walk-forward evidence fold_id does not match assigned fold")
    if (
        assignment.target_kind is EvidenceTargetKind.ROBUSTNESS_CHALLENGE
        and snapshot.challenge_id != assignment.target_id
    ):
        raise ValueError("robustness evidence challenge_id does not match assigned challenge")


def _target_label(kind: EvidenceTargetKind, target_id: str) -> str:
    return f"{kind.value}:{target_id}"


def _format_issue(label: str, values: tuple[str, ...]) -> str:
    if not values:
        return ""
    return f"{label}={list(values)!r}"
