"""Integrity-checked registry for Phase 1 runtime evidence kept outside Git."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.acceptance import DataFoundationCriterion


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceArtifact:
    """One immutable reference to a locally produced Phase 1 evidence artifact."""

    artifact_id: str
    criterion: DataFoundationCriterion
    path: Path
    sha256: str
    producer: str
    provider_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("runtime evidence artifact_id must be non-empty")
        if not self.producer.strip():
            raise ValueError("runtime evidence producer must be non-empty")
        if self.path.is_absolute():
            raise ValueError("runtime evidence paths must be relative to the configured evidence root")
        if not self.path.parts or ".." in self.path.parts:
            raise ValueError("runtime evidence path must stay within the configured evidence root")
        normalized_checksum = self.sha256.strip().lower()
        if len(normalized_checksum) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_checksum
        ):
            raise ValueError("runtime evidence sha256 must be a 64-character hexadecimal digest")
        if any(not provider_id.strip() for provider_id in self.provider_ids):
            raise ValueError("runtime evidence provider IDs must be non-empty")


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceVerification:
    """Verification result retaining the expected and observed evidence checksums."""

    artifact: RuntimeEvidenceArtifact
    exists: bool
    checksum_matches: bool
    observed_sha256: str | None

    @property
    def verified(self) -> bool:
        return self.exists and self.checksum_matches


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceRegistry:
    """Unique collection of immutable runtime evidence references."""

    artifacts: tuple[RuntimeEvidenceArtifact, ...]

    def __post_init__(self) -> None:
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("runtime evidence artifact IDs must be unique")

    def for_criterion(
        self,
        criterion: DataFoundationCriterion,
    ) -> tuple[RuntimeEvidenceArtifact, ...]:
        return tuple(artifact for artifact in self.artifacts if artifact.criterion is criterion)

    def verify(self, root: Path) -> tuple[RuntimeEvidenceVerification, ...]:
        """Verify every registered artifact without changing acceptance state."""

        return tuple(verify_runtime_evidence(artifact, root=root) for artifact in self.artifacts)


def verify_runtime_evidence(
    artifact: RuntimeEvidenceArtifact,
    *,
    root: Path,
) -> RuntimeEvidenceVerification:
    """Verify one referenced artifact by exact bytes and fail closed when it is absent."""

    target = root / artifact.path
    if not target.is_file():
        return RuntimeEvidenceVerification(
            artifact=artifact,
            exists=False,
            checksum_matches=False,
            observed_sha256=None,
        )
    observed = _sha256_file(target)
    return RuntimeEvidenceVerification(
        artifact=artifact,
        exists=True,
        checksum_matches=observed == artifact.sha256.lower(),
        observed_sha256=observed,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
