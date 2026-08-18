"""Durable research-brain containers built on immutable experiment evidence.

A research brain is a focused, append-only collection of experiment references. It is not a model,
a strategy optimizer, or a promotion engine. Brain membership preserves positive, null, failed, and
unfavorable research so later conditioning can synthesize the complete history rather than only
survivors.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import cast

from trade_scout.experiments.contracts import (
    ExperimentManifest,
    ExperimentStatus,
    JSONScalar,
    JSONValue,
)
from trade_scout.experiments.serialization import canonical_json, sha256_json


class ResearchBrainError(RuntimeError):
    """Raised when a research-brain record is unsafe or internally inconsistent."""


class BrainAlignmentState(StrEnum):
    """Deterministic scope assessment for one experiment added to a brain."""

    IN_SCOPE = "IN_SCOPE"
    DRIFT_WARNING = "DRIFT_WARNING"
    UNASSESSED = "UNASSESSED"


@dataclass(frozen=True, slots=True)
class BrainFocusRule:
    """One explicit resolved-configuration constraint defining a brain's focus envelope."""

    configuration_path: str
    allowed_values: tuple[JSONScalar, ...]
    rationale: str

    def __post_init__(self) -> None:
        if not self.configuration_path.strip():
            raise ValueError("brain focus-rule path must be non-empty")
        if any(not part.strip() for part in self.configuration_path.split(".")):
            raise ValueError("brain focus-rule path contains an empty segment")
        if not self.allowed_values:
            raise ValueError("brain focus rule requires at least one allowed value")
        if not self.rationale.strip():
            raise ValueError("brain focus-rule rationale must be non-empty")


@dataclass(frozen=True, slots=True)
class ResearchBrainDefinition:
    """Immutable definition of one research question and its optional focus envelope."""

    brain_id: str
    name: str
    research_question: str
    created_by: str
    created_at: str
    focus_rules: tuple[BrainFocusRule, ...] = ()
    notes: str = ""
    version: str = "research-brain-definition-v0.1"

    def __post_init__(self) -> None:
        _safe_identifier(self.brain_id, "brain_id")
        required = {
            "name": self.name,
            "research_question": self.research_question,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "version": self.version,
        }
        empty = tuple(key for key, value in required.items() if not value.strip())
        if empty:
            raise ValueError(f"research brain has empty required fields: {', '.join(empty)}")
        _aware_timestamp(self.created_at, "created_at")
        paths = tuple(rule.configuration_path for rule in self.focus_rules)
        if len(paths) != len(set(paths)):
            raise ValueError("research brain focus-rule paths must be unique")


@dataclass(frozen=True, slots=True)
class BrainExperimentMembership:
    """Append-only binding from one brain to one checksum-verified terminal experiment."""

    membership_id: str
    brain_id: str
    experiment_id: str
    experiment_manifest_checksum: str
    experiment_status: ExperimentStatus
    added_by: str
    added_at: str
    alignment_state: BrainAlignmentState
    alignment_reasons: tuple[str, ...]
    note: str = ""
    version: str = "research-brain-membership-v0.1"

    def __post_init__(self) -> None:
        _safe_identifier(self.membership_id, "membership_id")
        _safe_identifier(self.brain_id, "brain_id")
        _safe_identifier(self.experiment_id, "experiment_id")
        if self.experiment_status not in {ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED}:
            raise ValueError("brain membership requires a terminal experiment")
        if not self.experiment_manifest_checksum.strip():
            raise ValueError("brain membership requires an experiment manifest checksum")
        if not self.added_by.strip():
            raise ValueError("brain membership added_by must be non-empty")
        _aware_timestamp(self.added_at, "added_at")
        if self.alignment_state is BrainAlignmentState.IN_SCOPE and self.alignment_reasons:
            raise ValueError("IN_SCOPE brain membership must not carry drift reasons")
        if self.alignment_state is BrainAlignmentState.DRIFT_WARNING and not self.alignment_reasons:
            raise ValueError("DRIFT_WARNING brain membership requires reasons")
        if self.alignment_state is BrainAlignmentState.UNASSESSED and self.alignment_reasons:
            raise ValueError("UNASSESSED brain membership must not carry drift reasons")


@dataclass(frozen=True, slots=True)
class ResearchBrainSnapshot:
    """Current append-only brain inventory without inferring scientific conclusions."""

    definition: ResearchBrainDefinition
    memberships: tuple[BrainExperimentMembership, ...]
    succeeded_count: int
    failed_count: int
    in_scope_count: int
    drift_warning_count: int
    unassessed_count: int
    conditioning_readiness: str = "NOT_ASSESSED"
    conditioning_note: str = (
        "Conditioning readiness is not inferred from a fixed run-count threshold; it requires a "
        "separate evidence-sufficiency assessment."
    )


class FileResearchBrainStore:
    """Checksum-verified append-only filesystem store for research-brain knowledge."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def create(self, definition: ResearchBrainDefinition) -> str:
        """Create one immutable brain definition and return its checksum."""

        brain_dir = self._brain_dir(definition.brain_id)
        path = brain_dir / "definition.json"
        if path.exists():
            raise ResearchBrainError(f"research brain already exists: {definition.brain_id}")
        brain_dir.mkdir(parents=True, exist_ok=True)
        (brain_dir / "memberships").mkdir(parents=True, exist_ok=True)
        checksum = sha256_json(definition)
        _atomic_json(path, {"definition": definition, "checksum": checksum})
        return checksum

    def read_definition(self, brain_id: str) -> ResearchBrainDefinition:
        """Read and checksum-verify one immutable brain definition."""

        path = self._brain_dir(brain_id) / "definition.json"
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            definition_raw = cast(dict[str, object], raw["definition"])
            expected = str(raw["checksum"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchBrainError(f"cannot read research brain definition: {brain_id}") from exc
        definition = _definition_from_mapping(definition_raw)
        if definition.brain_id != brain_id:
            raise ResearchBrainError("research brain definition identity mismatch")
        if sha256_json(definition) != expected:
            raise ResearchBrainError(f"research brain definition checksum mismatch: {brain_id}")
        return definition

    def add_experiment(
        self,
        brain_id: str,
        manifest: ExperimentManifest,
        *,
        added_by: str,
        note: str = "",
        added_at: datetime | None = None,
    ) -> BrainExperimentMembership:
        """Append one experiment reference; drift warns but never erases the research record."""

        definition = self.read_definition(brain_id)
        if manifest.status not in {ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED}:
            raise ResearchBrainError("only terminal experiments may be added to a research brain")
        if manifest.manifest_checksum is None:
            raise ResearchBrainError(
                "experiment manifest must be checksum-verified before membership"
            )
        _safe_identifier(manifest.experiment_id, "experiment_id")
        if not added_by.strip():
            raise ValueError("added_by must be non-empty")
        membership_path = self._membership_path(brain_id, manifest.experiment_id)
        if membership_path.exists():
            raise ResearchBrainError(
                f"experiment already belongs to research brain: {manifest.experiment_id}"
            )

        alignment, reasons = assess_brain_alignment(definition, manifest)
        timestamp = added_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("added_at must be timezone-aware")
        timestamp = timestamp.astimezone(UTC)
        membership = BrainExperimentMembership(
            membership_id=_membership_id(brain_id, manifest.experiment_id),
            brain_id=brain_id,
            experiment_id=manifest.experiment_id,
            experiment_manifest_checksum=manifest.manifest_checksum,
            experiment_status=manifest.status,
            added_by=added_by.strip(),
            added_at=timestamp.isoformat(),
            alignment_state=alignment,
            alignment_reasons=reasons,
            note=note.strip(),
        )
        checksum = sha256_json(membership)
        membership_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(membership_path, {"membership": membership, "checksum": checksum})
        return membership

    def read_membership(self, brain_id: str, experiment_id: str) -> BrainExperimentMembership:
        """Read and checksum-verify one brain membership record."""

        path = self._membership_path(brain_id, experiment_id)
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            membership_raw = cast(dict[str, object], raw["membership"])
            expected = str(raw["checksum"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchBrainError(
                f"cannot read research brain membership: {brain_id}/{experiment_id}"
            ) from exc
        membership = _membership_from_mapping(membership_raw)
        if membership.brain_id != brain_id or membership.experiment_id != experiment_id:
            raise ResearchBrainError("research brain membership identity mismatch")
        if sha256_json(membership) != expected:
            raise ResearchBrainError(
                f"research brain membership checksum mismatch: {brain_id}/{experiment_id}"
            )
        return membership

    def memberships(self, brain_id: str) -> tuple[BrainExperimentMembership, ...]:
        """Return the full preserved brain membership history, including failed experiments."""

        self.read_definition(brain_id)
        root = self._brain_dir(brain_id) / "memberships"
        if not root.exists():
            return ()
        items = tuple(
            self.read_membership(brain_id, path.stem) for path in sorted(root.glob("*.json"))
        )
        return tuple(sorted(items, key=lambda item: (item.added_at, item.membership_id)))

    def snapshot(self, brain_id: str) -> ResearchBrainSnapshot:
        """Return inventory without choosing winners or assessing evidence sufficiency."""

        definition = self.read_definition(brain_id)
        memberships = self.memberships(brain_id)
        return ResearchBrainSnapshot(
            definition=definition,
            memberships=memberships,
            succeeded_count=sum(
                item.experiment_status is ExperimentStatus.SUCCEEDED for item in memberships
            ),
            failed_count=sum(
                item.experiment_status is ExperimentStatus.FAILED for item in memberships
            ),
            in_scope_count=sum(
                item.alignment_state is BrainAlignmentState.IN_SCOPE for item in memberships
            ),
            drift_warning_count=sum(
                item.alignment_state is BrainAlignmentState.DRIFT_WARNING for item in memberships
            ),
            unassessed_count=sum(
                item.alignment_state is BrainAlignmentState.UNASSESSED for item in memberships
            ),
        )

    def list_brains(self) -> tuple[ResearchBrainDefinition, ...]:
        """Return every checksum-verified brain definition under this store."""

        if not self._root.exists():
            return ()
        definitions: list[ResearchBrainDefinition] = []
        for path in sorted(self._root.glob("*/definition.json")):
            definitions.append(self.read_definition(path.parent.name))
        return tuple(definitions)

    def verify_membership_experiment(
        self,
        brain_id: str,
        manifest: ExperimentManifest,
    ) -> BrainExperimentMembership:
        """Verify that a referenced experiment still matches the checksum recorded at membership."""

        membership = self.read_membership(brain_id, manifest.experiment_id)
        if manifest.manifest_checksum != membership.experiment_manifest_checksum:
            raise ResearchBrainError(
                f"experiment manifest changed after brain membership: {manifest.experiment_id}"
            )
        if manifest.status is not membership.experiment_status:
            raise ResearchBrainError(
                f"experiment status changed after brain membership: {manifest.experiment_id}"
            )
        return membership

    def _brain_dir(self, brain_id: str) -> Path:
        _safe_identifier(brain_id, "brain_id")
        return self._root / brain_id

    def _membership_path(self, brain_id: str, experiment_id: str) -> Path:
        _safe_identifier(experiment_id, "experiment_id")
        return self._brain_dir(brain_id) / "memberships" / f"{experiment_id}.json"


def assess_brain_alignment(
    definition: ResearchBrainDefinition,
    manifest: ExperimentManifest,
) -> tuple[BrainAlignmentState, tuple[str, ...]]:
    """Assess explicit focus rules; mismatches warn but never block membership."""

    if not definition.focus_rules:
        return BrainAlignmentState.UNASSESSED, ()
    reasons: list[str] = []
    configuration = manifest.definition.resolved_configuration
    for rule in definition.focus_rules:
        found, value = _configuration_value(configuration, rule.configuration_path)
        if not found:
            reasons.append(f"missing focus path {rule.configuration_path!r}: {rule.rationale}")
            continue
        if value not in rule.allowed_values:
            allowed = ", ".join(repr(item) for item in rule.allowed_values)
            reasons.append(
                f"{rule.configuration_path}={value!r} is outside allowed [{allowed}]: "
                f"{rule.rationale}"
            )
    if reasons:
        return BrainAlignmentState.DRIFT_WARNING, tuple(reasons)
    return BrainAlignmentState.IN_SCOPE, ()


def _configuration_value(
    configuration: dict[str, JSONValue],
    path: str,
) -> tuple[bool, JSONValue | None]:
    current: JSONValue = configuration
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _membership_id(brain_id: str, experiment_id: str) -> str:
    digest = sha256(f"{brain_id}\n{experiment_id}".encode()).hexdigest()[:24]
    return f"brainmem_{digest}"


def _definition_from_mapping(raw: dict[str, object]) -> ResearchBrainDefinition:
    rules = tuple(
        BrainFocusRule(
            configuration_path=str(item["configuration_path"]),
            allowed_values=tuple(cast(list[JSONScalar], item["allowed_values"])),
            rationale=str(item["rationale"]),
        )
        for item in cast(list[dict[str, object]], raw.get("focus_rules", []))
    )
    return ResearchBrainDefinition(
        brain_id=str(raw["brain_id"]),
        name=str(raw["name"]),
        research_question=str(raw["research_question"]),
        created_by=str(raw["created_by"]),
        created_at=str(raw["created_at"]),
        focus_rules=rules,
        notes=str(raw.get("notes", "")),
        version=str(raw.get("version", "research-brain-definition-v0.1")),
    )


def _membership_from_mapping(raw: dict[str, object]) -> BrainExperimentMembership:
    return BrainExperimentMembership(
        membership_id=str(raw["membership_id"]),
        brain_id=str(raw["brain_id"]),
        experiment_id=str(raw["experiment_id"]),
        experiment_manifest_checksum=str(raw["experiment_manifest_checksum"]),
        experiment_status=ExperimentStatus(str(raw["experiment_status"])),
        added_by=str(raw["added_by"]),
        added_at=str(raw["added_at"]),
        alignment_state=BrainAlignmentState(str(raw["alignment_state"])),
        alignment_reasons=tuple(
            str(item) for item in cast(list[object], raw.get("alignment_reasons", []))
        ),
        note=str(raw.get("note", "")),
        version=str(raw.get("version", "research-brain-membership-v0.1")),
    )


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    temporary.replace(path)


def _safe_identifier(value: str, field: str) -> str:
    resolved = value.strip()
    if not resolved or any(character in resolved for character in "/\\"):
        raise ValueError(f"{field} must be a non-empty path-safe identifier")
    return resolved


def _aware_timestamp(value: str, field: str) -> datetime:
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return resolved


__all__ = [
    "BrainAlignmentState",
    "BrainExperimentMembership",
    "BrainFocusRule",
    "FileResearchBrainStore",
    "ResearchBrainDefinition",
    "ResearchBrainError",
    "ResearchBrainSnapshot",
    "assess_brain_alignment",
]
