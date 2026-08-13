"""Immutable checksum-verified persistence for complete validation review bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from trade_scout.validation.completeness import (
    EvidenceAssignment,
    EvidenceTargetKind,
    ValidationCompleteness,
)
from trade_scout.validation.contracts import SampleAccounting
from trade_scout.validation.evidence import (
    ComparatorDefinition,
    ComparatorKind,
    ConfidenceInterval,
    EffectEstimate,
    EvidenceRole,
    EvidenceSnapshot,
    MetricEstimate,
    ValidationEvidenceReport,
)
from trade_scout.validation.multiplicity import (
    AdjustedPValue,
    HypothesisFamily,
    MultiplicityMethod,
)
from trade_scout.validation.parameter_surface import ParameterAxis, ParameterCell, ParameterSurface
from trade_scout.validation.reporting import (
    MultiplicitySummary,
    ValidationReviewBundle,
    ValidationRoleCount,
)

_SCHEMA_VERSION = 1


class ValidationReviewStoreError(RuntimeError):
    """Raised when a persisted validation review cannot be trusted or reconstructed."""


class FileValidationReviewStore:
    """Append-only filesystem store for complete validation review bundles.

    Every bundle is serialized deterministically, wrapped with its SHA-256 checksum, and written
    atomically. Existing report IDs are immutable. Reads verify schema version, checksum, path/file
    identity, and all nested dataclass invariants before returning a bundle.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, bundle: ValidationReviewBundle) -> str:
        """Persist one review exactly once and return its deterministic payload checksum."""

        report_id = bundle.report.report_id
        path = self._path(report_id)
        self._root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValidationReviewStoreError(f"validation review already exists: {report_id}")

        payload = _bundle_to_mapping(bundle)
        checksum = _sha256_mapping(payload)
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "report_id": report_id,
            "checksum": checksum,
            "bundle": payload,
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(_canonical_json(envelope) + "\n", encoding="utf-8")
        temporary.replace(path)
        return checksum

    def read(self, report_id: str) -> ValidationReviewBundle:
        """Read one review after fail-closed envelope, checksum, and identity verification."""

        path = self._path(report_id)
        try:
            raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise ValidationReviewStoreError(f"validation review not found: {report_id}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationReviewStoreError(
                f"validation review is unreadable: {report_id}: {exc}"
            ) from exc

        if raw.get("schema_version") != _SCHEMA_VERSION:
            raise ValidationReviewStoreError(
                f"unsupported validation review schema for {report_id}: "
                f"{raw.get('schema_version')!r}"
            )
        if raw.get("report_id") != report_id:
            raise ValidationReviewStoreError(
                f"validation review file identity mismatch: expected {report_id}, "
                f"got {raw.get('report_id')!r}"
            )
        payload = raw.get("bundle")
        checksum = raw.get("checksum")
        if not isinstance(payload, dict) or not isinstance(checksum, str):
            raise ValidationReviewStoreError(
                f"validation review envelope is malformed: {report_id}"
            )
        actual = _sha256_mapping(payload)
        if actual != checksum:
            raise ValidationReviewStoreError(f"validation review checksum mismatch: {report_id}")

        try:
            bundle = _bundle_from_mapping(cast(dict[str, Any], payload))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationReviewStoreError(
                f"validation review payload is invalid: {report_id}: {exc}"
            ) from exc
        if bundle.report.report_id != report_id:
            raise ValidationReviewStoreError(
                f"validation review payload identity mismatch: expected {report_id}, "
                f"got {bundle.report.report_id}"
            )
        return bundle

    def checksum(self, report_id: str) -> str:
        """Return the verified deterministic checksum for one persisted review."""

        bundle = self.read(report_id)
        return _sha256_mapping(_bundle_to_mapping(bundle))

    def list_report_ids(self) -> tuple[str, ...]:
        """Return persisted report IDs in deterministic order without trusting file contents."""

        if not self._root.exists():
            return ()
        return tuple(path.stem for path in sorted(self._root.glob("*.json")))

    def _path(self, report_id: str) -> Path:
        if not report_id or not report_id.strip():
            raise ValueError("report_id must be non-empty")
        if report_id != report_id.strip() or any(character in report_id for character in "/\\"):
            raise ValueError("report_id must be a path-safe identifier")
        if report_id in {".", ".."}:
            raise ValueError("report_id must be a path-safe identifier")
        return self._root / f"{report_id}.json"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_mapping(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _bundle_to_mapping(bundle: ValidationReviewBundle) -> dict[str, Any]:
    return cast(dict[str, Any], asdict(bundle))


def _bundle_from_mapping(raw: dict[str, Any]) -> ValidationReviewBundle:
    return ValidationReviewBundle(
        report=_report_from_mapping(_mapping(raw, "report")),
        assignments=tuple(
            _assignment_from_mapping(item) for item in _mapping_list(raw, "assignments")
        ),
        completeness=_completeness_from_mapping(_mapping(raw, "completeness")),
        role_counts=tuple(
            _role_count_from_mapping(item) for item in _mapping_list(raw, "role_counts")
        ),
        parameter_surfaces=tuple(
            _surface_from_mapping(item) for item in _mapping_list(raw, "parameter_surfaces")
        ),
        multiplicity=tuple(
            _multiplicity_summary_from_mapping(item) for item in _mapping_list(raw, "multiplicity")
        ),
        robustness_plan_id=_optional_string(raw.get("robustness_plan_id")),
    )


def _report_from_mapping(raw: dict[str, Any]) -> ValidationEvidenceReport:
    return ValidationEvidenceReport(
        report_id=_string(raw, "report_id"),
        experiment_id=_string(raw, "experiment_id"),
        validation_plan_id=_string(raw, "validation_plan_id"),
        primary_outcome=_string(raw, "primary_outcome"),
        snapshots=tuple(_snapshot_from_mapping(item) for item in _mapping_list(raw, "snapshots")),
        multiplicity_family_id=_optional_string(raw.get("multiplicity_family_id")),
        notes=_string_tuple(raw.get("notes", []), "notes"),
    )


def _snapshot_from_mapping(raw: dict[str, Any]) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        evidence_id=_string(raw, "evidence_id"),
        role=EvidenceRole(_string(raw, "role")),
        sample=_sample_from_mapping(_mapping(raw, "sample")),
        metrics=tuple(_metric_from_mapping(item) for item in _mapping_list(raw, "metrics")),
        effects=tuple(_effect_from_mapping(item) for item in _mapping_list(raw, "effects")),
        fold_id=_optional_string(raw.get("fold_id")),
        challenge_id=_optional_string(raw.get("challenge_id")),
        warnings=_string_tuple(raw.get("warnings", []), "warnings"),
    )


def _metric_from_mapping(raw: dict[str, Any]) -> MetricEstimate:
    return MetricEstimate(
        metric=_string(raw, "metric"),
        estimate=_float(raw, "estimate"),
        units=_string(raw, "units"),
        interval=_optional_interval(raw.get("interval")),
    )


def _effect_from_mapping(raw: dict[str, Any]) -> EffectEstimate:
    return EffectEstimate(
        effect_id=_string(raw, "effect_id"),
        metric=_string(raw, "metric"),
        estimate=_float(raw, "estimate"),
        units=_string(raw, "units"),
        comparator=_comparator_from_mapping(_mapping(raw, "comparator")),
        sample=_sample_from_mapping(_mapping(raw, "sample")),
        interval=_optional_interval(raw.get("interval")),
        p_value=_optional_float(raw.get("p_value"), "p_value"),
        adjusted_p_value=_optional_float(raw.get("adjusted_p_value"), "adjusted_p_value"),
    )


def _comparator_from_mapping(raw: dict[str, Any]) -> ComparatorDefinition:
    return ComparatorDefinition(
        comparator_id=_string(raw, "comparator_id"),
        kind=ComparatorKind(_string(raw, "kind")),
        description=_string(raw, "description"),
        matching_fields=_string_tuple(raw.get("matching_fields", []), "matching_fields"),
        random_seed=_optional_int(raw.get("random_seed"), "random_seed"),
    )


def _interval_from_mapping(raw: dict[str, Any]) -> ConfidenceInterval:
    return ConfidenceInterval(
        lower=_float(raw, "lower"),
        upper=_float(raw, "upper"),
        confidence_level=_float(raw, "confidence_level"),
        method=_string(raw, "method"),
    )


def _optional_interval(value: object) -> ConfidenceInterval | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("interval must be an object or null")
    return _interval_from_mapping(cast(dict[str, Any], value))


def _sample_from_mapping(raw: dict[str, Any]) -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=_int(raw, "raw_event_count"),
        unique_instrument_count=_int(raw, "unique_instrument_count"),
        effective_sample_size=_optional_float(
            raw.get("effective_sample_size"), "effective_sample_size"
        ),
        cluster_count=_optional_int(raw.get("cluster_count"), "cluster_count"),
        exclusions=_string_tuple(raw.get("exclusions", []), "exclusions"),
    )


def _assignment_from_mapping(raw: dict[str, Any]) -> EvidenceAssignment:
    return EvidenceAssignment(
        evidence_id=_string(raw, "evidence_id"),
        target_kind=EvidenceTargetKind(_string(raw, "target_kind")),
        target_id=_string(raw, "target_id"),
    )


def _completeness_from_mapping(raw: dict[str, Any]) -> ValidationCompleteness:
    complete = raw.get("complete")
    if not isinstance(complete, bool):
        raise TypeError("complete must be boolean")
    return ValidationCompleteness(
        complete=complete,
        missing_targets=_string_tuple(raw.get("missing_targets", []), "missing_targets"),
        unexpected_targets=_string_tuple(raw.get("unexpected_targets", []), "unexpected_targets"),
        role_mismatches=_string_tuple(raw.get("role_mismatches", []), "role_mismatches"),
        unassigned_evidence=_string_tuple(
            raw.get("unassigned_evidence", []), "unassigned_evidence"
        ),
    )


def _role_count_from_mapping(raw: dict[str, Any]) -> ValidationRoleCount:
    return ValidationRoleCount(
        role=EvidenceRole(_string(raw, "role")),
        count=_int(raw, "count"),
    )


def _surface_from_mapping(raw: dict[str, Any]) -> ParameterSurface:
    return ParameterSurface(
        surface_id=_string(raw, "surface_id"),
        axes=tuple(_axis_from_mapping(item) for item in _mapping_list(raw, "axes")),
        metric=_string(raw, "metric"),
        units=_string(raw, "units"),
        cells=tuple(_cell_from_mapping(item) for item in _mapping_list(raw, "cells")),
    )


def _axis_from_mapping(raw: dict[str, Any]) -> ParameterAxis:
    values = raw.get("values")
    if not isinstance(values, list):
        raise TypeError("parameter axis values must be a list")
    for value in values:
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError("unsupported parameter axis value")
    return ParameterAxis(name=_string(raw, "name"), values=tuple(values))


def _cell_from_mapping(raw: dict[str, Any]) -> ParameterCell:
    coordinates_raw = raw.get("coordinates")
    if not isinstance(coordinates_raw, list):
        raise TypeError("parameter cell coordinates must be a list")
    coordinates: list[tuple[str, str | int | float | bool]] = []
    for item in coordinates_raw:
        if not isinstance(item, list) or len(item) != 2:
            raise TypeError("parameter coordinate must be a two-item list")
        name, value = item
        if not isinstance(name, str) or not isinstance(value, (str, int, float, bool)):
            raise TypeError("invalid parameter coordinate")
        coordinates.append((name, value))
    return ParameterCell(
        coordinates=tuple(coordinates),
        metric=_string(raw, "metric"),
        estimate=_float(raw, "estimate"),
        units=_string(raw, "units"),
        sample=_sample_from_mapping(_mapping(raw, "sample")),
        interval=_optional_interval(raw.get("interval")),
        warnings=_string_tuple(raw.get("warnings", []), "warnings"),
    )


def _multiplicity_summary_from_mapping(raw: dict[str, Any]) -> MultiplicitySummary:
    return MultiplicitySummary(
        family=_family_from_mapping(_mapping(raw, "family")),
        adjusted_values=tuple(
            _adjusted_p_from_mapping(item) for item in _mapping_list(raw, "adjusted_values")
        ),
    )


def _family_from_mapping(raw: dict[str, Any]) -> HypothesisFamily:
    return HypothesisFamily(
        family_id=_string(raw, "family_id"),
        hypothesis_ids=_string_tuple(raw.get("hypothesis_ids", []), "hypothesis_ids"),
        method=MultiplicityMethod(_string(raw, "method")),
        alpha=_float(raw, "alpha"),
    )


def _adjusted_p_from_mapping(raw: dict[str, Any]) -> AdjustedPValue:
    return AdjustedPValue(
        hypothesis_id=_string(raw, "hypothesis_id"),
        raw_p_value=_float(raw, "raw_p_value"),
        adjusted_p_value=_float(raw, "adjusted_p_value"),
    )


def _mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return cast(dict[str, Any], value)


def _mapping_list(raw: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise TypeError(f"{key} entries must be objects")
        result.append(cast(dict[str, Any], item))
    return tuple(result)


def _string(raw: dict[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _string_tuple(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a list of strings")
    return tuple(cast(list[str], value))


def _float(raw: dict[str, Any], key: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _int(raw: dict[str, Any], key: str) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional string field must be a string or null")
    return value


def _optional_float(value: object, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric or null")
    return float(value)


def _optional_int(value: object, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer or null")
    return value
