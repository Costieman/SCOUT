"""Cryptographic provenance binding for persisted statistical validation reviews.

The provenance layer binds one immutable validation review to the frozen validation design and the
checksum-verified experiment manifest whose stage artifacts supplied the research evidence. It
proves identity and lineage relationships only; it never infers statistical credibility or a
research decision state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from trade_scout.experiments.contracts import ExperimentManifest, ExperimentStatus
from trade_scout.experiments.serialization import sha256_json
from trade_scout.validation.completeness import assess_validation_completeness
from trade_scout.validation.contracts import ValidationPlan
from trade_scout.validation.reporting import ValidationReviewBundle
from trade_scout.validation.robustness import RobustnessPlan

_SCHEMA_VERSION = 1


class ValidationReviewProvenanceError(RuntimeError):
    """Raised when validation-review lineage cannot be trusted or reproduced."""


@dataclass(frozen=True, slots=True)
class StageArtifactProvenance:
    """Checksum identity of one persisted experiment stage artifact."""

    stage_name: str
    output_checksum: str

    def __post_init__(self) -> None:
        if not self.stage_name.strip():
            raise ValueError("stage_name must be non-empty")
        _require_sha256(self.output_checksum, "output_checksum")


@dataclass(frozen=True, slots=True)
class ValidationReviewProvenance:
    """Immutable cryptographic binding from review to design and experiment evidence."""

    report_id: str
    review_checksum: str
    validation_plan_id: str
    validation_plan_checksum: str
    experiment_id: str
    experiment_manifest_checksum: str
    stage_artifacts: tuple[StageArtifactProvenance, ...]
    robustness_plan_id: str | None = None
    robustness_plan_checksum: str | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("report_id", self.report_id),
            ("validation_plan_id", self.validation_plan_id),
            ("experiment_id", self.experiment_id),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        _require_sha256(self.review_checksum, "review_checksum")
        _require_sha256(self.validation_plan_checksum, "validation_plan_checksum")
        _require_sha256(self.experiment_manifest_checksum, "experiment_manifest_checksum")
        names = tuple(item.stage_name for item in self.stage_artifacts)
        if len(names) != len(set(names)):
            raise ValueError("stage artifact names must be unique")
        if (self.robustness_plan_id is None) != (self.robustness_plan_checksum is None):
            raise ValueError("robustness plan identity and checksum must be supplied together")
        if self.robustness_plan_id is not None:
            if not self.robustness_plan_id.strip():
                raise ValueError("robustness_plan_id must be non-empty")
            assert self.robustness_plan_checksum is not None
            _require_sha256(self.robustness_plan_checksum, "robustness_plan_checksum")


class ValidationReviewChecksumReader(Protocol):
    """Minimal persisted-review contract required for provenance verification."""

    def checksum(self, report_id: str) -> str: ...

    def read(self, report_id: str) -> ValidationReviewBundle: ...


class FileValidationReviewProvenanceStore:
    """Append-only checksum-verified store for validation lineage attestations."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, provenance: ValidationReviewProvenance) -> str:
        """Persist one provenance record exactly once and return its envelope checksum."""

        path = self._path(provenance.report_id)
        self._root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValidationReviewProvenanceError(
                f"validation review provenance already exists: {provenance.report_id}"
            )
        payload = _provenance_to_mapping(provenance)
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

    def read(self, report_id: str) -> ValidationReviewProvenance:
        """Read one provenance record after schema, identity, and checksum verification."""

        path = self._path(report_id)
        try:
            raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise ValidationReviewProvenanceError(
                f"validation review provenance not found: {report_id}"
            ) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationReviewProvenanceError(
                f"validation review provenance is unreadable: {report_id}: {exc}"
            ) from exc
        if raw.get("schema_version") != _SCHEMA_VERSION:
            raise ValidationReviewProvenanceError(
                f"unsupported validation review provenance schema for {report_id}: "
                f"{raw.get('schema_version')!r}"
            )
        if raw.get("report_id") != report_id:
            raise ValidationReviewProvenanceError(
                f"validation review provenance identity mismatch: expected {report_id}, "
                f"got {raw.get('report_id')!r}"
            )
        payload = raw.get("provenance")
        checksum = raw.get("checksum")
        if not isinstance(payload, dict) or not isinstance(checksum, str):
            raise ValidationReviewProvenanceError(
                f"validation review provenance envelope is malformed: {report_id}"
            )
        if _sha256_mapping(cast(dict[str, Any], payload)) != checksum:
            raise ValidationReviewProvenanceError(
                f"validation review provenance checksum mismatch: {report_id}"
            )
        try:
            provenance = _provenance_from_mapping(cast(dict[str, Any], payload))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationReviewProvenanceError(
                f"validation review provenance payload is invalid: {report_id}: {exc}"
            ) from exc
        if provenance.report_id != report_id:
            raise ValidationReviewProvenanceError(
                f"validation review provenance payload identity mismatch: expected {report_id}, "
                f"got {provenance.report_id}"
            )
        return provenance

    def checksum(self, report_id: str) -> str:
        """Return the deterministic checksum of one verified provenance payload."""

        return _sha256_mapping(_provenance_to_mapping(self.read(report_id)))

    def _path(self, report_id: str) -> Path:
        if not report_id or report_id != report_id.strip():
            raise ValueError("report_id must be a non-empty path-safe identifier")
        if any(character in report_id for character in "/\\") or report_id in {".", ".."}:
            raise ValueError("report_id must be a non-empty path-safe identifier")
        return self._root / f"{report_id}.json"


def build_validation_review_provenance(
    *,
    bundle: ValidationReviewBundle,
    review_checksum: str,
    plan: ValidationPlan,
    experiment_manifest: ExperimentManifest,
    robustness_plan: RobustnessPlan | None = None,
) -> ValidationReviewProvenance:
    """Build lineage only after reproducing design coverage and manifest integrity."""

    report = bundle.report
    if report.validation_plan_id != plan.plan_id:
        raise ValidationReviewProvenanceError("review validation plan identity does not match plan")
    if report.experiment_id != experiment_manifest.experiment_id:
        raise ValidationReviewProvenanceError("review experiment identity does not match manifest")
    if experiment_manifest.status is not ExperimentStatus.SUCCEEDED:
        raise ValidationReviewProvenanceError("source experiment manifest must be SUCCEEDED")
    expected_manifest_checksum = experiment_manifest.manifest_checksum
    if expected_manifest_checksum is None:
        raise ValidationReviewProvenanceError("source experiment manifest has no checksum")
    actual_manifest_checksum = sha256_json(
        replace(experiment_manifest, manifest_checksum=None)
    )
    if actual_manifest_checksum != expected_manifest_checksum:
        raise ValidationReviewProvenanceError("source experiment manifest checksum mismatch")

    reproduced = assess_validation_completeness(
        plan=plan,
        report=report,
        assignments=bundle.assignments,
        robustness_plan=robustness_plan,
    )
    reproduced.require_complete()
    if reproduced != bundle.completeness:
        raise ValidationReviewProvenanceError(
            "persisted review completeness does not reproduce from supplied validation design"
        )
    expected_robustness_id = robustness_plan.plan_id if robustness_plan is not None else None
    if bundle.robustness_plan_id != expected_robustness_id:
        raise ValidationReviewProvenanceError("review robustness plan identity does not match plan")

    _require_sha256(review_checksum, "review_checksum")
    stage_artifacts = tuple(
        StageArtifactProvenance(stage.stage_name, stage.output_checksum)
        for stage in experiment_manifest.stages
    )
    return ValidationReviewProvenance(
        report_id=report.report_id,
        review_checksum=review_checksum,
        validation_plan_id=plan.plan_id,
        validation_plan_checksum=_sha256_validation_object(plan),
        experiment_id=experiment_manifest.experiment_id,
        experiment_manifest_checksum=expected_manifest_checksum,
        stage_artifacts=stage_artifacts,
        robustness_plan_id=expected_robustness_id,
        robustness_plan_checksum=(
            _sha256_validation_object(robustness_plan) if robustness_plan is not None else None
        ),
    )


def verify_validation_review_provenance(
    provenance: ValidationReviewProvenance,
    *,
    review_store: ValidationReviewChecksumReader,
    plan: ValidationPlan,
    experiment_manifest: ExperimentManifest,
    robustness_plan: RobustnessPlan | None = None,
) -> ValidationReviewBundle:
    """Reproduce the provenance binding against persisted review and supplied frozen sources."""

    bundle = review_store.read(provenance.report_id)
    review_checksum = review_store.checksum(provenance.report_id)
    rebuilt = build_validation_review_provenance(
        bundle=bundle,
        review_checksum=review_checksum,
        plan=plan,
        experiment_manifest=experiment_manifest,
        robustness_plan=robustness_plan,
    )
    if rebuilt != provenance:
        raise ValidationReviewProvenanceError(
            f"validation review provenance binding mismatch: {provenance.report_id}"
        )
    return bundle


def _provenance_to_mapping(provenance: ValidationReviewProvenance) -> dict[str, Any]:
    return {
        "report_id": provenance.report_id,
        "review_checksum": provenance.review_checksum,
        "validation_plan_id": provenance.validation_plan_id,
        "validation_plan_checksum": provenance.validation_plan_checksum,
        "experiment_id": provenance.experiment_id,
        "experiment_manifest_checksum": provenance.experiment_manifest_checksum,
        "stage_artifacts": [
            {"stage_name": item.stage_name, "output_checksum": item.output_checksum}
            for item in provenance.stage_artifacts
        ],
        "robustness_plan_id": provenance.robustness_plan_id,
        "robustness_plan_checksum": provenance.robustness_plan_checksum,
    }


def _provenance_from_mapping(raw: dict[str, Any]) -> ValidationReviewProvenance:
    stage_raw = raw.get("stage_artifacts")
    if not isinstance(stage_raw, list):
        raise TypeError("stage_artifacts must be a list")
    stages: list[StageArtifactProvenance] = []
    for item in stage_raw:
        if not isinstance(item, dict):
            raise TypeError("stage_artifacts entries must be objects")
        stages.append(
            StageArtifactProvenance(
                stage_name=_string(cast(dict[str, Any], item), "stage_name"),
                output_checksum=_string(cast(dict[str, Any], item), "output_checksum"),
            )
        )
    return ValidationReviewProvenance(
        report_id=_string(raw, "report_id"),
        review_checksum=_string(raw, "review_checksum"),
        validation_plan_id=_string(raw, "validation_plan_id"),
        validation_plan_checksum=_string(raw, "validation_plan_checksum"),
        experiment_id=_string(raw, "experiment_id"),
        experiment_manifest_checksum=_string(raw, "experiment_manifest_checksum"),
        stage_artifacts=tuple(stages),
        robustness_plan_id=_optional_string(raw.get("robustness_plan_id")),
        robustness_plan_checksum=_optional_string(raw.get("robustness_plan_checksum")),
    )


def _sha256_validation_object(value: object) -> str:
    return hashlib.sha256(_canonical_validation_json(value).encode("utf-8")).hexdigest()


def _canonical_validation_json(value: object) -> str:
    return json.dumps(
        _validation_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validation_json_value(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _validation_json_value(value.value)
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _validation_json_value(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): _validation_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_validation_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported validation provenance value: {type(value).__name__}")


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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional provenance identity must be a string or null")
    return value
