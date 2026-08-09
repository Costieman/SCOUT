from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.acceptance import DataFoundationCriterion
from trade_scout.data.runtime_evidence_manifest import (
    RuntimeEvidenceManifestError,
    load_runtime_evidence_manifest,
)


def _write_manifest(path: Path, *, criterion: str = "cross_provider_validation") -> None:
    path.write_text(
        json.dumps(
            {
                "manifest_version": "trade-scout-runtime-evidence-v0.1",
                "artifacts": [
                    {
                        "artifact_id": "sample",
                        "criterion": criterion,
                        "path": "alpha-tiingo/report/cross-provider-evidence.json",
                        "sha256": "a" * 64,
                        "producer": "scripts/run_alpha_tiingo_cross_validation.py",
                        "provider_ids": ["alpha_vantage", "tiingo"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_manifest_loads_strict_runtime_evidence_registry(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest)

    registry = load_runtime_evidence_manifest(manifest)

    assert len(registry.artifacts) == 1
    artifact = registry.artifacts[0]
    assert artifact.criterion is DataFoundationCriterion.CROSS_PROVIDER_VALIDATION
    assert artifact.provider_ids == ("alpha_vantage", "tiingo")


def test_manifest_rejects_unknown_acceptance_criterion(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, criterion="invented_gate")

    with pytest.raises(RuntimeEvidenceManifestError, match="criterion is unknown"):
        load_runtime_evidence_manifest(manifest)


def test_manifest_rejects_unsupported_version(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"manifest_version": "future", "artifacts": []}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeEvidenceManifestError, match="version is unsupported"):
        load_runtime_evidence_manifest(manifest)
