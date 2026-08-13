"""Cryptographic provenance for validation child experiments.

This layer binds one persisted validation-review provenance record to the complete ordered set of
Experiment Runner child manifests that produced validation evidence. It proves execution identity,
parent lineage, target identity, and persisted artifact checksums only; it does not infer scientific
credibility or promotion status.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast

from trade_scout.experiments.contracts import ExperimentManifest, ExperimentStatus
from trade_scout.experiments.serialization import sha256_json
from trade_scout.experiments.validation_provenance import StageArtifactProvenance

_SCHEMA_VERSION = 1
_TARGET_KEY = "_validation_target"


class ValidationChildProvenanceError(RuntimeError):
    """Raised when child-experiment validation lineage cannot be trusted."""


@dataclass(frozen=True, slots=True)
class ValidationChildExperimentProvenance:
    """Immutable identity for one validation child experiment and its stage artifacts."""

    target_id: str
    experiment_id: str
    manifest_checksum: str
    stage_artifacts: tuple[StageArtifactProvenance, ...]

    def __post_init__(self) -> None:
        if not self.target_id.strip():
            raise ValueError("target_id must be non-empty")
        if not self.experiment_id.strip():
            raise ValueError("experiment_id must be non-empty")
        _require_sha256(self.manifest_checksum, "manifest_checksum")
        names = tuple(item.stage_name for item in self.stage_artifacts)
        if len(names) != len(set(names)):
            raise ValueError("child stage artifact names must be unique")


@dataclass(frozen=True, slots=True)
class ValidationChildSetProvenance:
    """Binding from one review provenance record to all validation child executions."""

    report_id: str
    validation_plan_id: str
    source_experiment_id: str
    review_provenance_checksum: str
    children: tuple[ValidationChildExperimentProvenance, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("report_id", self.report_id),
            ("validation_plan_id", self.validation_plan_id),
            ("source_experiment_id", self.source_experiment_id),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        _require_sha256(self.review_provenance_checksum, "review_provenance_checksum")
        if not self.children:
            raise ValueError("validation child provenance must contain at least one child")
        target_ids = tuple(child.target_id for child in self.children)
        experiment_ids = tuple(child.experiment_id for child in self.children)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("validation child target IDs must be unique")
        if len(experiment_ids) != len(set(experiment_ids)):
            raise ValueError("validation child experiment IDs must be unique")


class ValidationChildManifestReader(Protocol):
    """Read checksum-verified experiment manifests by immutable experiment ID."""

    def read_manifest(self, experiment_id: str) -> ExperimentManifest: ...


class FileValidationChildProvenanceStore:
    """Append-only checksum-verified store for child-experiment lineage bindings."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, provenance: ValidationChildSetProvenance) -> str:
        path = self._path(provenance.report_id)
        self._root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValidationChildProvenanceError(
                f"validation child provenance already exists: {provenance.report_id}"
            )
        payload = _to_mapping(provenance)
        checksum = _sha256_mapping(payload)
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "report_id": provenance.report_id,
            "checksum": checksum,
            "provenance": payload,
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(_canonical_json(envelope) + "\n", encoding="utf-8")
        temporary.replace(path)
        return checksum

    def read(self, report_id: str) -> ValidationChildSetProvenance:
        path = self._path(report_id)
        try:
            raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise ValidationChildProvenanceError(
                f"validation child provenance not found: {report_id}"
            ) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationChildProvenanceError(
                f"validation child provenance is unreadable: {report_id}: {exc}"
            ) from exc
        if raw.get("schema_version") != _SCHEMA_VERSION or raw.get("report_id") != report_id:
            raise ValidationChildProvenanceError(
                f"validation child provenance envelope identity/schema mismatch: {report_id}"
            )
        payload = raw.get("provenance")
        checksum = raw.get("checksum")
        if not isinstance(payload, dict) or not isinstance(checksum, str):
            raise ValidationChildProvenanceError(
                f"validation child provenance envelope is malformed: {report_id}"
            )
        typed_payload = cast(dict[str, Any], payload)
        if _sha256_mapping(typed_payload) != checksum:
            raise ValidationChildProvenanceError(
                f"validation child provenance checksum mismatch: {report_id}"
            )
        try:
            provenance = _from_mapping(typed_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationChildProvenanceError(
                f"validation child provenance payload is invalid: {report_id}: {exc}"
            ) from exc
        if provenance.report_id != report_id:
            raise ValidationChildProvenanceError(
                f"validation child provenance payload identity mismatch: {report_id}"
            )
        return provenance

    def checksum(self, report_id: str) -> str:
        return _sha256_mapping(_to_mapping(self.read(report_id)))

    def _path(self, report_id: str) -> Path:
        if not report_id or report_id != report_id.strip():
            raise ValueError("report_id must be a non-empty path-safe identifier")
        if any(character in report_id for character in "/\\") or report_id in {".", ".."}:
            raise ValueError("report_id must be a non-empty path-safe identifier")
        return self._root / f"{report_id}.json"


def build_validation_child_provenance(
    *,
    report_id: str,
    validation_plan_id: str,
    source_experiment_id: str,
    review_provenance_checksum: str,
    child_manifests: tuple[ExperimentManifest, ...],
    expected_target_ids: tuple[str, ...],
) -> ValidationChildSetProvenance:
    """Build an ordered child-execution binding after fail-closed lineage verification."""

    _require_sha256(review_provenance_checksum, "review_provenance_checksum")
    if not child_manifests:
        raise ValidationChildProvenanceError("validation child manifest set is empty")
    if len(child_manifests) != len(expected_target_ids):
        raise ValidationChildProvenanceError(
            "validation child manifest count does not match declared validation target count"
        )

    children: list[ValidationChildExperimentProvenance] = []
    observed_targets: list[str] = []
    for manifest in child_manifests:
        child = _child_provenance(
            manifest,
            validation_plan_id=validation_plan_id,
            source_experiment_id=source_experiment_id,
        )
        children.append(child)
        observed_targets.append(child.target_id)

    if tuple(observed_targets) != expected_target_ids:
        raise ValidationChildProvenanceError(
            "validation child target order/identity does not match declared execution targets"
        )
    return ValidationChildSetProvenance(
        report_id=report_id,
        validation_plan_id=validation_plan_id,
        source_experiment_id=source_experiment_id,
        review_provenance_checksum=review_provenance_checksum,
        children=tuple(children),
    )


def verify_validation_child_provenance(
    provenance: ValidationChildSetProvenance,
    *,
    manifest_reader: ValidationChildManifestReader,
    current_review_provenance_checksum: str,
) -> None:
    """Rebuild the child binding from persisted manifests and require exact equality."""

    if current_review_provenance_checksum != provenance.review_provenance_checksum:
        raise ValidationChildProvenanceError("validation review provenance checksum changed")
    manifests = tuple(
        manifest_reader.read_manifest(child.experiment_id) for child in provenance.children
    )
    rebuilt = build_validation_child_provenance(
        report_id=provenance.report_id,
        validation_plan_id=provenance.validation_plan_id,
        source_experiment_id=provenance.source_experiment_id,
        review_provenance_checksum=current_review_provenance_checksum,
        child_manifests=manifests,
        expected_target_ids=tuple(child.target_id for child in provenance.children),
    )
    if rebuilt != provenance:
        raise ValidationChildProvenanceError(
            f"validation child provenance binding mismatch: {provenance.report_id}"
        )


def _child_provenance(
    manifest: ExperimentManifest,
    *,
    validation_plan_id: str,
    source_experiment_id: str,
) -> ValidationChildExperimentProvenance:
    if manifest.status is not ExperimentStatus.SUCCEEDED:
        raise ValidationChildProvenanceError(
            f"validation child experiment must be SUCCEEDED: {manifest.experiment_id}"
        )
    if manifest.definition.parent_experiment_id != source_experiment_id:
        raise ValidationChildProvenanceError(
            f"validation child parent lineage mismatch: {manifest.experiment_id}"
        )
    expected_checksum = manifest.manifest_checksum
    if expected_checksum is None:
        raise ValidationChildProvenanceError(
            f"validation child manifest has no checksum: {manifest.experiment_id}"
        )
    actual_checksum = sha256_json(replace(manifest, manifest_checksum=None))
    if actual_checksum != expected_checksum:
        raise ValidationChildProvenanceError(
            f"validation child manifest checksum mismatch: {manifest.experiment_id}"
        )
    metadata = manifest.definition.resolved_configuration.get(_TARGET_KEY)
    if not isinstance(metadata, dict):
        raise ValidationChildProvenanceError(
            f"validation child target metadata missing: {manifest.experiment_id}"
        )
    target_id = metadata.get("target_id")
    plan_id = metadata.get("validation_plan_id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValidationChildProvenanceError(
            f"validation child target identity missing: {manifest.experiment_id}"
        )
    if plan_id != validation_plan_id:
        raise ValidationChildProvenanceError(
            f"validation child plan identity mismatch: {manifest.experiment_id}"
        )
    return ValidationChildExperimentProvenance(
        target_id=target_id,
        experiment_id=manifest.experiment_id,
        manifest_checksum=expected_checksum,
        stage_artifacts=tuple(
            StageArtifactProvenance(stage.stage_name, stage.output_checksum)
            for stage in manifest.stages
        ),
    )


def _to_mapping(provenance: ValidationChildSetProvenance) -> dict[str, Any]:
    return {
        "report_id": provenance.report_id,
        "validation_plan_id": provenance.validation_plan_id,
        "source_experiment_id": provenance.source_experiment_id,
        "review_provenance_checksum": provenance.review_provenance_checksum,
        "children": [
            {
                "target_id": child.target_id,
                "experiment_id": child.experiment_id,
                "manifest_checksum": child.manifest_checksum,
                "stage_artifacts": [
                    {
                        "stage_name": stage.stage_name,
                        "output_checksum": stage.output_checksum,
                    }
                    for stage in child.stage_artifacts
                ],
            }
            for child in provenance.children
        ],
    }


def _from_mapping(raw: dict[str, Any]) -> ValidationChildSetProvenance:
    children_raw = raw.get("children")
    if not isinstance(children_raw, list):
        raise TypeError("children must be a list")
    children: list[ValidationChildExperimentProvenance] = []
    for item in children_raw:
        if not isinstance(item, dict):
            raise TypeError("children entries must be objects")
        item_mapping = cast(dict[str, Any], item)
        stages_raw = item_mapping.get("stage_artifacts")
        if not isinstance(stages_raw, list):
            raise TypeError("stage_artifacts must be a list")
        stages = tuple(
            StageArtifactProvenance(
                _string(cast(dict[str, Any], stage), "stage_name"),
                _string(cast(dict[str, Any], stage), "output_checksum"),
            )
            for stage in stages_raw
            if isinstance(stage, dict)
        )
        if len(stages) != len(stages_raw):
            raise TypeError("stage_artifacts entries must be objects")
        children.append(
            ValidationChildExperimentProvenance(
                target_id=_string(item_mapping, "target_id"),
                experiment_id=_string(item_mapping, "experiment_id"),
                manifest_checksum=_string(item_mapping, "manifest_checksum"),
                stage_artifacts=stages,
            )
        )
    return ValidationChildSetProvenance(
        report_id=_string(raw, "report_id"),
        validation_plan_id=_string(raw, "validation_plan_id"),
        source_experiment_id=_string(raw, "source_experiment_id"),
        review_provenance_checksum=_string(raw, "review_provenance_checksum"),
        children=tuple(children),
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_mapping(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hexadecimal digest")


def _string(raw: dict[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value
