"""Fail-closed registration of Phase 1 runtime evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trade_scout.data.evidence_bridge import assess_runtime_evidence
from trade_scout.data.runtime_evidence import RuntimeEvidenceArtifact
from trade_scout.data.runtime_evidence_manifest import load_runtime_evidence_manifest


class RuntimeEvidenceRegistrationError(ValueError):
    """Raised when runtime evidence cannot be safely registered."""


def register_runtime_evidence(
    *,
    report_path: Path,
    evidence_root: Path,
    manifest_path: Path,
    artifact_id: str,
    producer: str,
    provider_ids: tuple[str, ...] = (),
) -> RuntimeEvidenceArtifact:
    """Infer criterion from report semantics and register immutable bytes in a local manifest.

    Registration does not promote any acceptance criterion. It records the exact report checksum and
    the criterion derived by the conservative semantic bridge. Existing artifact IDs are idempotent
    only when every immutable field matches; conflicting reuse fails closed.
    """

    root = evidence_root.resolve()
    report = report_path.resolve()
    try:
        relative_path = report.relative_to(root)
    except ValueError as exc:
        raise RuntimeEvidenceRegistrationError(
            "runtime evidence report must be contained within the configured evidence root"
        ) from exc
    if not report.is_file():
        raise RuntimeEvidenceRegistrationError("runtime evidence report does not exist")

    assessment = assess_runtime_evidence(report)
    artifact = RuntimeEvidenceArtifact(
        artifact_id=artifact_id,
        criterion=assessment.evidence.criterion,
        path=relative_path,
        sha256=_sha256_file(report),
        producer=producer,
        provider_ids=provider_ids,
    )

    existing = _load_existing(manifest_path)
    by_id = {item.artifact_id: item for item in existing}
    prior = by_id.get(artifact.artifact_id)
    if prior is not None:
        if prior != artifact:
            raise RuntimeEvidenceRegistrationError(
                "runtime evidence artifact_id already exists with different immutable fields"
            )
        return prior

    artifacts = (*existing, artifact)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "trade-scout-runtime-evidence-v0.1",
                "artifacts": [_serialize(item) for item in artifacts],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact


def _load_existing(path: Path) -> tuple[RuntimeEvidenceArtifact, ...]:
    if not path.exists():
        return ()
    try:
        return load_runtime_evidence_manifest(path).artifacts
    except ValueError as exc:
        raise RuntimeEvidenceRegistrationError(
            "existing runtime evidence manifest is invalid"
        ) from exc


def _serialize(artifact: RuntimeEvidenceArtifact) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "criterion": artifact.criterion.value,
        "path": artifact.path.as_posix(),
        "sha256": artifact.sha256,
        "producer": artifact.producer,
        "provider_ids": list(artifact.provider_ids),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
