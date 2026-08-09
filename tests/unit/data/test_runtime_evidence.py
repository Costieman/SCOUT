from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from trade_scout.data.acceptance import DataFoundationCriterion
from trade_scout.data.runtime_evidence import (
    RuntimeEvidenceArtifact,
    RuntimeEvidenceRegistry,
    verify_runtime_evidence,
)


def _artifact(*, sha256: str) -> RuntimeEvidenceArtifact:
    return RuntimeEvidenceArtifact(
        artifact_id="alpha-tiingo-sample",
        criterion=DataFoundationCriterion.CROSS_PROVIDER_VALIDATION,
        path=Path("alpha-tiingo/report/cross-provider-evidence.json"),
        sha256=sha256,
        producer="scripts/run_alpha_tiingo_cross_validation.py",
        provider_ids=("alpha_vantage", "tiingo"),
    )


def test_verification_requires_exact_artifact_bytes(tmp_path: Path) -> None:
    payload = b'{"complete":true}\n'
    expected = hashlib.sha256(payload).hexdigest()
    target = tmp_path / "alpha-tiingo/report/cross-provider-evidence.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    verification = verify_runtime_evidence(_artifact(sha256=expected), root=tmp_path)

    assert verification.exists is True
    assert verification.checksum_matches is True
    assert verification.verified is True
    assert verification.observed_sha256 == expected


def test_changed_runtime_evidence_fails_integrity_check(tmp_path: Path) -> None:
    original = b'{"complete":true}\n'
    target = tmp_path / "alpha-tiingo/report/cross-provider-evidence.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"complete":false}\n')

    verification = verify_runtime_evidence(
        _artifact(sha256=hashlib.sha256(original).hexdigest()),
        root=tmp_path,
    )

    assert verification.exists is True
    assert verification.checksum_matches is False
    assert verification.verified is False


def test_missing_runtime_evidence_fails_closed(tmp_path: Path) -> None:
    verification = verify_runtime_evidence(_artifact(sha256="0" * 64), root=tmp_path)

    assert verification.exists is False
    assert verification.checksum_matches is False
    assert verification.observed_sha256 is None
    assert verification.verified is False


def test_registry_filters_by_acceptance_criterion() -> None:
    artifact = _artifact(sha256="a" * 64)
    registry = RuntimeEvidenceRegistry((artifact,))

    assert registry.for_criterion(DataFoundationCriterion.CROSS_PROVIDER_VALIDATION) == (artifact,)
    assert registry.for_criterion(DataFoundationCriterion.STORAGE_BENCHMARK) == ()


def test_registry_rejects_duplicate_artifact_ids() -> None:
    artifact = _artifact(sha256="b" * 64)

    with pytest.raises(ValueError, match="artifact IDs must be unique"):
        RuntimeEvidenceRegistry((artifact, artifact))


def test_artifact_path_cannot_escape_evidence_root() -> None:
    with pytest.raises(ValueError, match="stay within"):
        RuntimeEvidenceArtifact(
            artifact_id="escape",
            criterion=DataFoundationCriterion.CROSS_PROVIDER_VALIDATION,
            path=Path("../outside.json"),
            sha256="c" * 64,
            producer="fixture",
        )
