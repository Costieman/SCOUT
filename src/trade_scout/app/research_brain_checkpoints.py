"""Immutable checkpoints of descriptive research-brain reviews.

A checkpoint freezes what the browser review could say about a brain at one moment. It preserves
brain-definition identity, membership fingerprints, and the descriptive review payload without
promoting that review into scientific validation or analytical truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from trade_scout.app.research_brain_review import (
    BrainSweepObservation,
    ResearchBrainReview,
)
from trade_scout.experiments.research_brains import BrainExperimentMembership
from trade_scout.experiments.serialization import canonical_json, sha256_json

if TYPE_CHECKING:
    from trade_scout.app.research_brain_service import ResearchBrainView


class ResearchBrainCheckpointError(RuntimeError):
    """Raised when a checkpoint cannot be safely created or verified."""


@dataclass(frozen=True, slots=True)
class BrainMembershipFingerprint:
    """Exact brain-membership state included in one review checkpoint."""

    experiment_id: str
    membership_checksum: str
    experiment_manifest_checksum: str


@dataclass(frozen=True, slots=True)
class ResearchBrainReviewCheckpoint:
    """Immutable descriptive review snapshot tied to an exact brain membership set."""

    checkpoint_id: str
    brain_id: str
    created_at: str
    created_by: str
    brain_definition_checksum: str
    memberships: tuple[BrainMembershipFingerprint, ...]
    review: ResearchBrainReview
    note: str = ""
    version: str = "research-brain-review-checkpoint-v0.1"

    def __post_init__(self) -> None:
        if not self.checkpoint_id.strip() or any(
            character in self.checkpoint_id for character in "/\\"
        ):
            raise ValueError("checkpoint_id must be a non-empty path-safe identifier")
        if not self.brain_id.strip():
            raise ValueError("brain_id must be non-empty")
        if not self.created_by.strip():
            raise ValueError("created_by must be non-empty")
        if not self.brain_definition_checksum.strip():
            raise ValueError("brain_definition_checksum must be non-empty")
        _aware_timestamp(self.created_at)
        experiment_ids = tuple(item.experiment_id for item in self.memberships)
        if len(experiment_ids) != len(set(experiment_ids)):
            raise ValueError("checkpoint membership experiments must be unique")


class FileResearchBrainCheckpointStore:
    """Append-only checksum-verified store colocated with each private research brain."""

    def __init__(self, brain_root: Path) -> None:
        self._brain_root = brain_root

    def create(
        self,
        view: ResearchBrainView,
        review: ResearchBrainReview,
        *,
        created_by: str,
        note: str = "",
        created_at: datetime | None = None,
        checkpoint_id: str | None = None,
    ) -> ResearchBrainReviewCheckpoint:
        """Freeze one review against the exact brain definition and membership state."""

        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        actor = created_by.strip()
        if not actor:
            raise ValueError("created_by must be non-empty")
        definition = view.snapshot.definition
        resolved_id = checkpoint_id.strip() if checkpoint_id is not None else ""
        if not resolved_id:
            resolved_id = f"brainreview_{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        memberships = tuple(
            _membership_fingerprint(item.membership) for item in view.experiments
        )
        checkpoint = ResearchBrainReviewCheckpoint(
            checkpoint_id=resolved_id,
            brain_id=definition.brain_id,
            created_at=timestamp.astimezone(UTC).isoformat(),
            created_by=actor,
            brain_definition_checksum=sha256_json(definition),
            memberships=memberships,
            review=review,
            note=note.strip(),
        )
        path = self._checkpoint_path(checkpoint.brain_id, checkpoint.checkpoint_id)
        if path.exists():
            raise ResearchBrainCheckpointError(
                f"research brain review checkpoint already exists: {checkpoint.checkpoint_id}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        checksum = sha256_json(checkpoint)
        _atomic_json(path, {"checkpoint": checkpoint, "checksum": checksum})
        return checkpoint

    def read(self, brain_id: str, checkpoint_id: str) -> ResearchBrainReviewCheckpoint:
        """Read and verify one immutable review checkpoint."""

        path = self._checkpoint_path(brain_id, checkpoint_id)
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            checkpoint_raw = cast(dict[str, object], raw["checkpoint"])
            expected = str(raw["checksum"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchBrainCheckpointError(
                f"cannot read research brain review checkpoint: {brain_id}/{checkpoint_id}"
            ) from exc
        checkpoint = _checkpoint_from_mapping(checkpoint_raw)
        if checkpoint.brain_id != brain_id or checkpoint.checkpoint_id != checkpoint_id:
            raise ResearchBrainCheckpointError("research brain review checkpoint identity mismatch")
        if sha256_json(checkpoint) != expected:
            raise ResearchBrainCheckpointError(
                f"research brain review checkpoint checksum mismatch: {brain_id}/{checkpoint_id}"
            )
        return checkpoint

    def list(self, brain_id: str) -> tuple[ResearchBrainReviewCheckpoint, ...]:
        """Return every verified checkpoint for one brain, oldest first."""

        root = self._brain_root / brain_id / "reviews"
        if not root.exists():
            return ()
        checkpoints = tuple(self.read(brain_id, path.stem) for path in sorted(root.glob("*.json")))
        return tuple(sorted(checkpoints, key=lambda item: (item.created_at, item.checkpoint_id)))

    def verify_current_membership_state(
        self,
        checkpoint: ResearchBrainReviewCheckpoint,
        view: ResearchBrainView,
    ) -> bool:
        """Return whether the checkpoint still matches the brain's current definition/memberships."""

        if checkpoint.brain_id != view.snapshot.definition.brain_id:
            return False
        if checkpoint.brain_definition_checksum != sha256_json(view.snapshot.definition):
            return False
        current = tuple(_membership_fingerprint(item.membership) for item in view.experiments)
        return current == checkpoint.memberships

    def _checkpoint_path(self, brain_id: str, checkpoint_id: str) -> Path:
        if not brain_id.strip() or any(character in brain_id for character in "/\\"):
            raise ValueError("brain_id must be a non-empty path-safe identifier")
        if not checkpoint_id.strip() or any(character in checkpoint_id for character in "/\\"):
            raise ValueError("checkpoint_id must be a non-empty path-safe identifier")
        return self._brain_root / brain_id / "reviews" / f"{checkpoint_id}.json"


def _membership_fingerprint(
    membership: BrainExperimentMembership,
) -> BrainMembershipFingerprint:
    return BrainMembershipFingerprint(
        experiment_id=membership.experiment_id,
        membership_checksum=sha256_json(membership),
        experiment_manifest_checksum=membership.experiment_manifest_checksum,
    )


def _checkpoint_from_mapping(raw: dict[str, object]) -> ResearchBrainReviewCheckpoint:
    memberships = tuple(
        BrainMembershipFingerprint(
            experiment_id=str(item["experiment_id"]),
            membership_checksum=str(item["membership_checksum"]),
            experiment_manifest_checksum=str(item["experiment_manifest_checksum"]),
        )
        for item in cast(list[dict[str, object]], raw.get("memberships", []))
    )
    return ResearchBrainReviewCheckpoint(
        checkpoint_id=str(raw["checkpoint_id"]),
        brain_id=str(raw["brain_id"]),
        created_at=str(raw["created_at"]),
        created_by=str(raw["created_by"]),
        brain_definition_checksum=str(raw["brain_definition_checksum"]),
        memberships=memberships,
        review=_review_from_mapping(cast(dict[str, object], raw["review"])),
        note=str(raw.get("note", "")),
        version=str(raw.get("version", "research-brain-review-checkpoint-v0.1")),
    )


def _review_from_mapping(raw: dict[str, object]) -> ResearchBrainReview:
    sweeps = tuple(
        BrainSweepObservation(
            experiment_id=str(item["experiment_id"]),
            variable_label=str(item["variable_label"]),
            tested_values=int(item["tested_values"]),
            best_observed_value=_optional_float(item.get("best_observed_value")),
            best_observed_expectancy=_optional_float(item.get("best_observed_expectancy")),
            best_observed_complete_events=_optional_int(item.get("best_observed_complete_events")),
            worst_observed_value=_optional_float(item.get("worst_observed_value")),
            worst_observed_expectancy=_optional_float(item.get("worst_observed_expectancy")),
            smallest_complete_events=_optional_int(item.get("smallest_complete_events")),
            largest_complete_events=_optional_int(item.get("largest_complete_events")),
        )
        for item in cast(list[dict[str, object]], raw.get("sweep_observations", []))
    )
    return ResearchBrainReview(
        experiment_count=int(raw["experiment_count"]),
        succeeded_count=int(raw["succeeded_count"]),
        failed_count=int(raw["failed_count"]),
        sweep_count=int(raw["sweep_count"]),
        ordinary_run_count=int(raw["ordinary_run_count"]),
        drift_warning_count=int(raw["drift_warning_count"]),
        unreadable_evidence_count=int(raw["unreadable_evidence_count"]),
        sweep_observations=sweeps,
        findings=tuple(str(item) for item in cast(list[object], raw.get("findings", []))),
        cautions=tuple(str(item) for item in cast(list[object], raw.get("cautions", []))),
        next_questions=tuple(
            str(item) for item in cast(list[object], raw.get("next_questions", []))
        ),
        readiness_label=str(raw["readiness_label"]),
        readiness_explanation=str(raw["readiness_explanation"]),
    )


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if value is None:
        return None
    raise ResearchBrainCheckpointError("checkpoint float field has invalid type")


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if value is None:
        return None
    raise ResearchBrainCheckpointError("checkpoint integer field has invalid type")


def _aware_timestamp(value: str) -> datetime:
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("created_at must be an ISO timestamp") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    return resolved


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "BrainMembershipFingerprint",
    "FileResearchBrainCheckpointStore",
    "ResearchBrainCheckpointError",
    "ResearchBrainReviewCheckpoint",
]
