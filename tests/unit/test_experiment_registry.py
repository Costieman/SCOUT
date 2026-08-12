"""Tests for the DuckDB experiment registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
)
from trade_scout.experiments.registry import DuckDBExperimentRegistry, IndexedManifestStore
from trade_scout.experiments.store import FileManifestStore


def _manifest(
    experiment_id: str,
    *,
    status: ExperimentStatus = ExperimentStatus.SUCCEEDED,
    mode: ResearchMode = ResearchMode.EXPLORATORY,
    family: str | None = "consolidation_breakout",
    parent: str | None = None,
    reproduction_of: str | None = None,
    dataset_version: str = "dataset_v1",
) -> ExperimentManifest:
    definition = ExperimentDefinition(
        name=f"experiment_{experiment_id}",
        hypothesis="Synthetic registry hypothesis",
        mode=mode,
        dataset_version=dataset_version,
        universe_version="universe_v1",
        code_version="abc123",
        config_schema_version="0.1.0",
        resolved_configuration={"synthetic": True},
        hypothesis_family_id=family,
        parent_experiment_id=parent,
    )
    return ExperimentManifest(
        experiment_id=experiment_id,
        definition=definition,
        status=status,
        created_at="2026-08-13T00:00:00+00:00",
        completed_at="2026-08-13T00:01:00+00:00",
        manifest_checksum=f"checksum_{experiment_id}",
        reproduction_of=reproduction_of,
    )


def test_registry_upserts_latest_manifest_state(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    registry.register(_manifest("exp_1", status=ExperimentStatus.RUNNING))
    registry.register(_manifest("exp_1", status=ExperimentStatus.SUCCEEDED))

    assert registry.get("exp_1").status is ExperimentStatus.SUCCEEDED
    assert len(registry.query()) == 1


def test_registry_filters_by_governance_and_data_identity(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    registry.register(_manifest("exp_1", dataset_version="dataset_v1"))
    registry.register(
        _manifest(
            "exp_2",
            mode=ResearchMode.CONFIRMATORY,
            dataset_version="dataset_v2",
        )
    )

    confirmatory = registry.query(mode=ResearchMode.CONFIRMATORY)
    assert tuple(item.experiment_id for item in confirmatory) == ("exp_2",)

    dataset_v1 = registry.query(dataset_version="dataset_v1")
    assert tuple(item.experiment_id for item in dataset_v1) == ("exp_1",)


def test_registry_preserves_parent_child_lineage(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    registry.register(_manifest("exp_root"))
    registry.register(_manifest("exp_child", parent="exp_root"))
    registry.register(_manifest("exp_grandchild", parent="exp_child"))

    lineage = registry.lineage("exp_grandchild")
    assert tuple(item.experiment_id for item in lineage) == (
        "exp_root",
        "exp_child",
        "exp_grandchild",
    )


def test_registry_uses_reproduction_link_when_parent_is_absent(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    registry.register(_manifest("exp_source"))
    registry.register(_manifest("exp_repro", reproduction_of="exp_source"))

    lineage = registry.lineage("exp_repro")
    assert tuple(item.experiment_id for item in lineage) == ("exp_source", "exp_repro")


def test_indexed_store_registers_checksum_verified_manifest(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    store = IndexedManifestStore(FileManifestStore(tmp_path / "runs"), registry)

    store.write_manifest(_manifest("exp_indexed"))

    indexed = registry.get("exp_indexed")
    persisted = store.read_manifest("exp_indexed")
    assert indexed.manifest_checksum == persisted.manifest_checksum
    assert indexed.manifest_checksum is not None


def test_registry_unknown_experiment_fails_explicitly(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    with pytest.raises(KeyError):
        registry.get("missing")
