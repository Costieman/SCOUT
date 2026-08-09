from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.acceptance import DataFoundationCriterion
from trade_scout.data.runtime_evidence_manifest import load_runtime_evidence_manifest
from trade_scout.data.runtime_evidence_registration import (
    RuntimeEvidenceRegistrationError,
    register_runtime_evidence,
)


def _storage_report(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "eodhd-campaign-storage-evidence-v0.1",
                "dataset_version": "aggregate-v1",
                "representative_sample_accepted": True,
                "representative_sample": {"failures": []},
                "storage_benchmark": {
                    "record_count": 1_000_000,
                    "unique_instrument_count": 525,
                    "first_trade_date": "2018-01-02",
                    "last_trade_date": "2025-12-31",
                    "parquet_bytes": 123456,
                    "filtered_query_count": 1000,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_register_infers_criterion_and_persists_checksum(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    report = _storage_report(root / "storage.json")
    manifest = root / "manifest.json"

    artifact = register_runtime_evidence(
        report_path=report,
        evidence_root=root,
        manifest_path=manifest,
        artifact_id="storage-1",
        producer="run_eodhd_campaign_benchmark.py",
        provider_ids=("eodhd",),
    )

    assert artifact.criterion is DataFoundationCriterion.STORAGE_BENCHMARK
    registry = load_runtime_evidence_manifest(manifest)
    assert registry.artifacts == (artifact,)
    assert registry.verify(root)[0].verified


def test_register_is_idempotent_for_identical_artifact(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    report = _storage_report(root / "storage.json")
    manifest = root / "manifest.json"
    kwargs = {
        "report_path": report,
        "evidence_root": root,
        "manifest_path": manifest,
        "artifact_id": "storage-1",
        "producer": "runner",
    }

    first = register_runtime_evidence(**kwargs)
    second = register_runtime_evidence(**kwargs)

    assert second == first
    assert len(load_runtime_evidence_manifest(manifest).artifacts) == 1


def test_register_rejects_conflicting_artifact_id(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    report = _storage_report(root / "storage.json")
    manifest = root / "manifest.json"
    register_runtime_evidence(
        report_path=report,
        evidence_root=root,
        manifest_path=manifest,
        artifact_id="storage-1",
        producer="runner-a",
    )

    with pytest.raises(RuntimeEvidenceRegistrationError, match="already exists"):
        register_runtime_evidence(
            report_path=report,
            evidence_root=root,
            manifest_path=manifest,
            artifact_id="storage-1",
            producer="runner-b",
        )


def test_register_rejects_report_outside_evidence_root(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    report = _storage_report(tmp_path / "outside.json")

    with pytest.raises(RuntimeEvidenceRegistrationError, match="contained"):
        register_runtime_evidence(
            report_path=report,
            evidence_root=root,
            manifest_path=root / "manifest.json",
            artifact_id="storage-1",
            producer="runner",
        )
