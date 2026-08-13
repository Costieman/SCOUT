"""Append-only checksum-verified persistence for frozen validation designs."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, cast

from trade_scout.validation.contracts import (
    DateInterval,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    WalkForwardFold,
)
from trade_scout.validation.robustness import (
    RobustnessChallenge,
    RobustnessKind,
    RobustnessPlan,
)

_SCHEMA_VERSION = 1


class FrozenValidationPlanStoreError(RuntimeError):
    """Raised when a frozen validation design cannot be trusted or reconstructed."""


class FileValidationPlanStore:
    """Append-only store for immutable validation plans.

    Each plan is serialized deterministically, protected by a SHA-256 payload checksum, and written
    atomically. Existing plan identities are immutable. Reads verify schema, path/file identity,
    checksum integrity, and all typed contract invariants before returning a plan.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, plan: ValidationPlan) -> str:
        """Persist one validation plan exactly once and return its payload checksum."""

        return self._write("validation_plan", plan.plan_id, _validation_plan_to_mapping(plan))

    def read_validation_plan(self, plan_id: str) -> ValidationPlan:
        """Read one checksum-verified frozen validation plan."""

        payload = self._read("validation_plan", plan_id)
        try:
            plan = _validation_plan_from_mapping(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise FrozenValidationPlanStoreError(
                f"validation plan payload is invalid: {plan_id}: {exc}"
            ) from exc
        if plan.plan_id != plan_id:
            raise FrozenValidationPlanStoreError(
                f"validation plan payload identity mismatch: expected {plan_id}, got {plan.plan_id}"
            )
        return plan

    def checksum(self, plan_id: str) -> str:
        """Return the deterministic checksum of one verified validation plan."""

        plan = self.read_validation_plan(plan_id)
        return _sha256_mapping(_validation_plan_to_mapping(plan))

    def list_plan_ids(self) -> tuple[str, ...]:
        """Return known validation-plan identities in deterministic order."""

        return self._list_ids("validation_plan")

    def _write(self, kind: str, identity: str, payload: dict[str, Any]) -> str:
        path = self._path(kind, identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FrozenValidationPlanStoreError(f"{kind} already exists: {identity}")
        checksum = _sha256_mapping(payload)
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "kind": kind,
            "identity": identity,
            "checksum": checksum,
            "payload": payload,
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(_canonical_json(envelope) + "\n", encoding="utf-8")
        temporary.replace(path)
        return checksum

    def _read(self, kind: str, identity: str) -> dict[str, Any]:
        path = self._path(kind, identity)
        try:
            raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise FrozenValidationPlanStoreError(f"{kind} not found: {identity}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FrozenValidationPlanStoreError(
                f"{kind} is unreadable: {identity}: {exc}"
            ) from exc
        _verify_envelope(raw, expected_kind=kind, expected_identity=identity)
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise FrozenValidationPlanStoreError(f"{kind} envelope is malformed: {identity}")
        return cast(dict[str, Any], payload)

    def _list_ids(self, kind: str) -> tuple[str, ...]:
        directory = self._root / kind
        if not directory.exists():
            return ()
        return tuple(path.stem for path in sorted(directory.glob("*.json")))

    def _path(self, kind: str, identity: str) -> Path:
        _require_path_safe(identity, "plan identity")
        return self._root / kind / f"{identity}.json"


class FileRobustnessPlanStore:
    """Append-only checksum-verified store for immutable robustness plans."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, plan: RobustnessPlan) -> str:
        """Persist one robustness plan exactly once and return its payload checksum."""

        path = self._path(plan.plan_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FrozenValidationPlanStoreError(f"robustness_plan already exists: {plan.plan_id}")
        payload = _robustness_plan_to_mapping(plan)
        checksum = _sha256_mapping(payload)
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "kind": "robustness_plan",
            "identity": plan.plan_id,
            "checksum": checksum,
            "payload": payload,
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(_canonical_json(envelope) + "\n", encoding="utf-8")
        temporary.replace(path)
        return checksum

    def read_robustness_plan(self, plan_id: str) -> RobustnessPlan:
        """Read one checksum-verified frozen robustness plan."""

        path = self._path(plan_id)
        try:
            raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise FrozenValidationPlanStoreError(f"robustness_plan not found: {plan_id}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FrozenValidationPlanStoreError(
                f"robustness_plan is unreadable: {plan_id}: {exc}"
            ) from exc
        _verify_envelope(raw, expected_kind="robustness_plan", expected_identity=plan_id)
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise FrozenValidationPlanStoreError(
                f"robustness_plan envelope is malformed: {plan_id}"
            )
        try:
            plan = _robustness_plan_from_mapping(cast(dict[str, Any], payload))
        except (KeyError, TypeError, ValueError) as exc:
            raise FrozenValidationPlanStoreError(
                f"robustness plan payload is invalid: {plan_id}: {exc}"
            ) from exc
        if plan.plan_id != plan_id:
            raise FrozenValidationPlanStoreError(
                f"robustness plan payload identity mismatch: expected {plan_id}, got {plan.plan_id}"
            )
        return plan

    def checksum(self, plan_id: str) -> str:
        """Return the deterministic checksum of one verified robustness plan."""

        return _sha256_mapping(_robustness_plan_to_mapping(self.read_robustness_plan(plan_id)))

    def list_plan_ids(self) -> tuple[str, ...]:
        """Return known robustness-plan identities in deterministic order."""

        directory = self._root / "robustness_plan"
        if not directory.exists():
            return ()
        return tuple(path.stem for path in sorted(directory.glob("*.json")))

    def _path(self, plan_id: str) -> Path:
        _require_path_safe(plan_id, "plan identity")
        return self._root / "robustness_plan" / f"{plan_id}.json"


def _verify_envelope(
    raw: dict[str, Any],
    *,
    expected_kind: str,
    expected_identity: str,
) -> None:
    if raw.get("schema_version") != _SCHEMA_VERSION:
        raise FrozenValidationPlanStoreError(
            f"unsupported {expected_kind} schema for {expected_identity}: "
            f"{raw.get('schema_version')!r}"
        )
    if raw.get("kind") != expected_kind:
        raise FrozenValidationPlanStoreError(
            f"{expected_kind} kind mismatch: expected {expected_kind}, got {raw.get('kind')!r}"
        )
    if raw.get("identity") != expected_identity:
        raise FrozenValidationPlanStoreError(
            f"{expected_kind} file identity mismatch: expected {expected_identity}, "
            f"got {raw.get('identity')!r}"
        )
    payload = raw.get("payload")
    checksum = raw.get("checksum")
    if not isinstance(payload, dict) or not isinstance(checksum, str):
        raise FrozenValidationPlanStoreError(
            f"{expected_kind} envelope is malformed: {expected_identity}"
        )
    if _sha256_mapping(cast(dict[str, Any], payload)) != checksum:
        raise FrozenValidationPlanStoreError(
            f"{expected_kind} checksum mismatch: {expected_identity}"
        )


def _validation_plan_to_mapping(plan: ValidationPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "segments": [
            {
                "segment_id": segment.segment_id,
                "role": segment.role.value,
                "interval": {
                    "start": segment.interval.start.isoformat(),
                    "end": segment.interval.end.isoformat(),
                },
            }
            for segment in plan.segments
        ],
        "walk_forward_folds": [
            {
                "fold_id": fold.fold_id,
                "development": {
                    "start": fold.development.start.isoformat(),
                    "end": fold.development.end.isoformat(),
                },
                "validation": {
                    "start": fold.validation.start.isoformat(),
                    "end": fold.validation.end.isoformat(),
                },
            }
            for fold in plan.walk_forward_folds
        ],
        "primary_outcome": plan.primary_outcome,
        "comparator_id": plan.comparator_id,
        "robustness_checks": list(plan.robustness_checks),
        "notes": list(plan.notes),
    }


def _validation_plan_from_mapping(raw: dict[str, Any]) -> ValidationPlan:
    segments_raw = _list_of_mappings(raw, "segments")
    folds_raw = _list_of_mappings(raw, "walk_forward_folds")
    return ValidationPlan(
        plan_id=_string(raw, "plan_id"),
        segments=tuple(
            ValidationSegment(
                segment_id=_string(item, "segment_id"),
                role=ValidationRole(_string(item, "role")),
                interval=_interval_from_mapping(_mapping(item, "interval")),
            )
            for item in segments_raw
        ),
        walk_forward_folds=tuple(
            WalkForwardFold(
                fold_id=_string(item, "fold_id"),
                development=_interval_from_mapping(_mapping(item, "development")),
                validation=_interval_from_mapping(_mapping(item, "validation")),
            )
            for item in folds_raw
        ),
        primary_outcome=_optional_string(raw.get("primary_outcome")),
        comparator_id=_optional_string(raw.get("comparator_id")),
        robustness_checks=_string_tuple(raw.get("robustness_checks"), "robustness_checks"),
        notes=_string_tuple(raw.get("notes"), "notes"),
    )


def _robustness_plan_to_mapping(plan: RobustnessPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "challenges": [
            {
                "challenge_id": challenge.challenge_id,
                "kind": challenge.kind.value,
                "description": challenge.description,
                "changed_fields": list(challenge.changed_fields),
            }
            for challenge in plan.challenges
        ],
    }


def _robustness_plan_from_mapping(raw: dict[str, Any]) -> RobustnessPlan:
    return RobustnessPlan(
        plan_id=_string(raw, "plan_id"),
        challenges=tuple(
            RobustnessChallenge(
                challenge_id=_string(item, "challenge_id"),
                kind=RobustnessKind(_string(item, "kind")),
                description=_string(item, "description"),
                changed_fields=_string_tuple(item.get("changed_fields"), "changed_fields"),
            )
            for item in _list_of_mappings(raw, "challenges")
        ),
    )


def _interval_from_mapping(raw: dict[str, Any]) -> DateInterval:
    return DateInterval(
        start=_date(raw, "start"),
        end=_date(raw, "end"),
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_mapping(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_path_safe(value: str, label: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty path-safe identifier")
    if any(character in value for character in "/\\") or value in {".", ".."}:
        raise ValueError(f"{label} must be a non-empty path-safe identifier")


def _mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return cast(dict[str, Any], value)


def _list_of_mappings(raw: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional identity must be a string or null")
    return value


def _string_tuple(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a list of strings")
    return tuple(cast(list[str], value))


def _date(raw: dict[str, Any], key: str) -> date:
    value = _string(raw, key)
    return date.fromisoformat(value)
