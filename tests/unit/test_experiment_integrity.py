"""Tests for persisted experiment-manifest and stage-artifact integrity auditing."""

from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.integrity import (
    ExperimentIntegrityError,
    StageIntegrityState,
    audit_experiment,
)
from trade_scout.experiments.registry import DuckDBExperimentRegistry, IndexedManifestStore
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _Stage:
    @property
    def name(self) -> str:
        return "measure"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={"experiment_id": context.experiment_id, "value": 42},
        )


def _definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="integrity_fixture",
        hypothesis="Synthetic persistence integrity hypothesis",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="dataset_v1",
        universe_version="universe_v1",
        code_version="abc123",
        config_schema_version="0.1.0",
        resolved_configuration={"synthetic": True},
    )


def _run(tmp_path: Path) -> tuple[FileManifestStore, str]:
    store = FileManifestStore(tmp_path / "runs")
    runner = ExperimentRunner(store, id_factory=lambda: "exp_integrity")
    manifest = runner.run(_definition(), (_Stage(),))
    return store, manifest.experiment_id


def test_intact_experiment_verifies_manifest_and_stage_outputs(tmp_path: Path) -> None:
    store, experiment_id = _run(tmp_path)

    report = audit_experiment(store, experiment_id)

    assert report.verified
    assert report.manifest_verified
    assert len(report.stages) == 1
    assert report.stages[0].state is StageIntegrityState.VERIFIED
    report.require_verified()


def test_missing_stage_artifact_is_visible_and_blocks_verification(tmp_path: Path) -> None:
    store, experiment_id = _run(tmp_path)
    artifact = tmp_path / "runs" / experiment_id / "artifacts" / "measure.json"
    artifact.unlink()

    report = audit_experiment(store, experiment_id)

    assert not report.verified
    assert report.stages[0].state is StageIntegrityState.MISSING
    with pytest.raises(ExperimentIntegrityError, match="measure:MISSING"):
        report.require_verified()


def test_tampered_stage_artifact_reports_checksum_mismatch(tmp_path: Path) -> None:
    store, experiment_id = _run(tmp_path)
    artifact = tmp_path / "runs" / experiment_id / "artifacts" / "measure.json"
    text = artifact.read_text(encoding="utf-8")
    artifact.write_text(text.replace("42", "43"), encoding="utf-8")

    report = audit_experiment(store, experiment_id)

    assert not report.verified
    assert report.stages[0].state is StageIntegrityState.CHECKSUM_MISMATCH
    assert report.stages[0].actual_checksum != report.stages[0].expected_checksum


def test_invalid_manifest_returns_visible_manifest_failure(tmp_path: Path) -> None:
    store, experiment_id = _run(tmp_path)
    path = tmp_path / "runs" / experiment_id / "manifest.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("dataset_v1", "dataset_tampered"), encoding="utf-8")

    report = audit_experiment(store, experiment_id)

    assert not report.verified
    assert not report.manifest_verified
    assert report.stages == ()
    assert "checksum mismatch" in report.manifest_detail


def test_unreadable_stage_output_is_distinct_from_missing_output(tmp_path: Path) -> None:
    store, experiment_id = _run(tmp_path)
    artifact = tmp_path / "runs" / experiment_id / "artifacts" / "measure.json"
    artifact.write_text("not-json\n", encoding="utf-8")

    report = audit_experiment(store, experiment_id)

    assert report.stages[0].state is StageIntegrityState.UNREADABLE


def test_indexed_manifest_store_preserves_stage_output_read_contract(tmp_path: Path) -> None:
    base_store = FileManifestStore(tmp_path / "runs")
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    store = IndexedManifestStore(base_store, registry)
    runner = ExperimentRunner(store, id_factory=lambda: "exp_indexed")
    runner.run(_definition(), (_Stage(),))

    output = store.read_stage_output("exp_indexed", "measure")
    report = audit_experiment(store, "exp_indexed")

    assert output["value"] == 42
    assert report.verified
