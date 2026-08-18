"""Small file-backed store for user-created Strategy Builder suites.

Built-in suites remain code-defined and immutable.  This store persists only user-owned copies and
custom suites so the application can offer build, duplicate, edit, save, reload, and delete workflows
without turning UI state into analytical truth.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from trade_scout.app.strategy_suite_registry import (
    StrategySuite,
    SuiteEvidenceClass,
    SuiteImplementationKind,
    SuiteImplementationStatus,
)


class StrategySuiteStore:
    """Persist user-owned strategy suites as deterministic JSON documents."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, suite: StrategySuite) -> Path:
        """Atomically save one custom/derived suite and return its path."""

        if suite.built_in:
            raise ValueError(
                "built-in suites are immutable and must not be persisted as user suites"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(suite.suite_id)
        payload = _suite_payload(suite)
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=self.root, text=True
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return path

    def load(self, suite_id: str) -> StrategySuite:
        """Load one previously persisted user suite."""

        path = self._path(suite_id)
        if not path.exists():
            raise KeyError(f"saved strategy suite {suite_id!r} does not exist")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("strategy suite payload must be a JSON object")
        suite = _suite_from_payload(payload)
        if suite.built_in:
            raise ValueError("saved strategy suite payload cannot claim built-in ownership")
        return suite

    def list(self) -> tuple[StrategySuite, ...]:
        """Return all saved user suites in stable id order."""

        if not self.root.exists():
            return ()
        suites = [self.load(path.stem) for path in self.root.glob("*.json")]
        return tuple(sorted(suites, key=lambda item: item.suite_id.casefold()))

    def delete(self, suite_id: str) -> None:
        """Delete one saved user suite explicitly."""

        path = self._path(suite_id)
        if not path.exists():
            raise KeyError(f"saved strategy suite {suite_id!r} does not exist")
        path.unlink()

    def _path(self, suite_id: str) -> Path:
        safe = _safe_id(suite_id)
        return self.root / f"{safe}.json"


def _safe_id(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("strategy suite id must be non-empty")
    if any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in text
    ):
        raise ValueError(
            "strategy suite id may contain only letters, numbers, hyphen, and underscore"
        )
    return text


def _suite_payload(suite: StrategySuite) -> dict[str, Any]:
    payload = asdict(suite)
    payload["evidence_class"] = suite.evidence_class.value
    payload["implementation_kind"] = suite.implementation_kind.value
    payload["implementation_status"] = suite.implementation_status.value
    payload["canonical_recipe"] = list(suite.canonical_recipe)
    payload["required_capabilities"] = list(suite.required_capabilities)
    payload["parameter_axes"] = list(suite.parameter_axes)
    payload["source_basis"] = list(suite.source_basis)
    return payload


def _suite_from_payload(payload: dict[str, Any]) -> StrategySuite:
    required = {
        "suite_id",
        "name",
        "family",
        "evidence_class",
        "implementation_kind",
        "implementation_status",
        "canonical_timeframe",
        "description",
        "canonical_recipe",
        "required_capabilities",
        "parameter_axes",
        "source_basis",
        "version",
        "built_in",
        "editable",
    }
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"strategy suite payload missing fields: {sorted(missing)}")
    return StrategySuite(
        suite_id=str(payload["suite_id"]),
        name=str(payload["name"]),
        family=str(payload["family"]),
        evidence_class=SuiteEvidenceClass(str(payload["evidence_class"])),
        implementation_kind=SuiteImplementationKind(str(payload["implementation_kind"])),
        implementation_status=SuiteImplementationStatus(str(payload["implementation_status"])),
        canonical_timeframe=str(payload["canonical_timeframe"]),
        description=str(payload["description"]),
        canonical_recipe=tuple(str(item) for item in payload["canonical_recipe"]),
        required_capabilities=tuple(str(item) for item in payload["required_capabilities"]),
        parameter_axes=tuple(str(item) for item in payload["parameter_axes"]),
        source_basis=tuple(str(item) for item in payload["source_basis"]),
        version=str(payload["version"]),
        built_in=bool(payload["built_in"]),
        editable=bool(payload["editable"]),
    )


__all__ = ["StrategySuiteStore"]
