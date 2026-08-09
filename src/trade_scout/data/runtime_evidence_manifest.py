"""JSON manifest loading for integrity-checked Phase 1 runtime evidence."""

from __future__ import annotations

import json
from pathlib import Path

from trade_scout.data.acceptance import DataFoundationCriterion
from trade_scout.data.runtime_evidence import RuntimeEvidenceArtifact, RuntimeEvidenceRegistry


class RuntimeEvidenceManifestError(ValueError):
    """Raised when a runtime evidence manifest violates the required schema."""


def load_runtime_evidence_manifest(path: Path) -> RuntimeEvidenceRegistry:
    """Load a strict JSON registry without treating referenced evidence as verified."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeEvidenceManifestError("runtime evidence manifest is unreadable") from exc
    if not isinstance(payload, dict):
        raise RuntimeEvidenceManifestError("runtime evidence manifest root must be an object")
    if payload.get("manifest_version") != "trade-scout-runtime-evidence-v0.1":
        raise RuntimeEvidenceManifestError("runtime evidence manifest version is unsupported")
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise RuntimeEvidenceManifestError("runtime evidence manifest artifacts must be a list")
    return RuntimeEvidenceRegistry(tuple(_parse_artifact(item) for item in raw_artifacts))


def _parse_artifact(raw: object) -> RuntimeEvidenceArtifact:
    if not isinstance(raw, dict):
        raise RuntimeEvidenceManifestError("runtime evidence artifact must be an object")
    required = {"artifact_id", "criterion", "path", "sha256", "producer"}
    missing = required - set(raw)
    if missing:
        details = ",".join(sorted(missing))
        raise RuntimeEvidenceManifestError(f"runtime evidence artifact missing fields: {details}")
    provider_ids = raw.get("provider_ids", [])
    if not isinstance(provider_ids, list) or any(not isinstance(item, str) for item in provider_ids):
        raise RuntimeEvidenceManifestError("runtime evidence provider_ids must be a string list")
    try:
        criterion = DataFoundationCriterion(str(raw["criterion"]))
    except ValueError as exc:
        raise RuntimeEvidenceManifestError("runtime evidence criterion is unknown") from exc
    return RuntimeEvidenceArtifact(
        artifact_id=str(raw["artifact_id"]),
        criterion=criterion,
        path=Path(str(raw["path"])),
        sha256=str(raw["sha256"]),
        producer=str(raw["producer"]),
        provider_ids=tuple(provider_ids),
    )
