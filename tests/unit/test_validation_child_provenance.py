"""Tests for validation child-experiment provenance bindings."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentManifest,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.validation_child_provenance import (
    FileValidationChildProvenanceStore,
    ValidationChildProvenanceError,
    build_validation_child_provenance,
    verify_validation_child_provenance,
)


class _Stage:
    name = "estimate"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(self.name, {"estimate": 0.01})


def _definition(parent: str, target_id: str) -> ExperimentDefinition:
    return ExperimentDefinition(
        name="validation child",
        hypothesis="Frozen validation execution.",
        mode=ResearchMode.CONFIRMATORY,
        dataset_version="dataset-v1",
        universe_version="universe-v1",
        code_version="code-v1",
        config_schema_version="1",
        resolved_configuration={
            "_validation_target": {"validation_plan_id": "plan-v1", "target_id": target_id}
        },
        parent_experiment_id=parent,
    )


def _child(store: FileManifestStore, experiment_id: str, target_id: str) -> ExperimentManifest:
    return ExperimentRunner(store, id_factory=lambda: experiment_id).run(
        _definition("source-exp", target_id), (_Stage(),)
    )


def test_builds_persists_and_reverifies_ordered_child_binding(tmp_path: Path) -> None:
    manifest_store = FileManifestStore(tmp_path / "manifests")
    first = _child(manifest_store, "child-1", "validation")
    second = _child(manifest_store, "child-2", "fold-1")
    provenance = build_validation_child_provenance(
        report_id="review-1",
        validation_plan_id="plan-v1",
        source_experiment_id="source-exp",
        review_provenance_checksum="a" * 64,
        child_manifests=(first, second),
        expected_target_ids=("validation", "fold-1"),
    )
    store = FileValidationChildProvenanceStore(tmp_path / "provenance")
    checksum = store.write(provenance)
    assert len(checksum) == 64
    assert store.read("review-1") == provenance
    assert tuple(child.target_id for child in provenance.children) == ("validation", "fold-1")
    verify_validation_child_provenance(
        provenance,
        manifest_reader=manifest_store,
        current_review_provenance_checksum="a" * 64,
    )


def test_rejects_missing_or_reordered_children(tmp_path: Path) -> None:
    manifest_store = FileManifestStore(tmp_path)
    first = _child(manifest_store, "child-1", "validation")
    second = _child(manifest_store, "child-2", "fold-1")
    with pytest.raises(ValidationChildProvenanceError, match="order/identity"):
        build_validation_child_provenance(
            report_id="review-1",
            validation_plan_id="plan-v1",
            source_experiment_id="source-exp",
            review_provenance_checksum="b" * 64,
            child_manifests=(first, second),
            expected_target_ids=("fold-1", "validation"),
        )
    with pytest.raises(ValidationChildProvenanceError, match="count"):
        build_validation_child_provenance(
            report_id="review-1",
            validation_plan_id="plan-v1",
            source_experiment_id="source-exp",
            review_provenance_checksum="b" * 64,
            child_manifests=(first,),
            expected_target_ids=("validation", "fold-1"),
        )


def test_rejects_parent_manifest_or_plan_identity_drift(tmp_path: Path) -> None:
    manifest_store = FileManifestStore(tmp_path)
    child = _child(manifest_store, "child-1", "validation")
    wrong_parent = replace(
        child, definition=replace(child.definition, parent_experiment_id="other")
    )
    with pytest.raises(ValidationChildProvenanceError, match="parent lineage"):
        build_validation_child_provenance(
            report_id="review-1",
            validation_plan_id="plan-v1",
            source_experiment_id="source-exp",
            review_provenance_checksum="c" * 64,
            child_manifests=(wrong_parent,),
            expected_target_ids=("validation",),
        )
    tampered = replace(child, warnings=("changed",))
    with pytest.raises(ValidationChildProvenanceError, match="checksum mismatch"):
        build_validation_child_provenance(
            report_id="review-1",
            validation_plan_id="plan-v1",
            source_experiment_id="source-exp",
            review_provenance_checksum="c" * 64,
            child_manifests=(tampered,),
            expected_target_ids=("validation",),
        )
    with pytest.raises(ValidationChildProvenanceError, match="plan identity"):
        build_validation_child_provenance(
            report_id="review-1",
            validation_plan_id="other-plan",
            source_experiment_id="source-exp",
            review_provenance_checksum="c" * 64,
            child_manifests=(child,),
            expected_target_ids=("validation",),
        )


def test_reverification_rejects_changed_review_provenance_checksum(tmp_path: Path) -> None:
    manifest_store = FileManifestStore(tmp_path)
    child = _child(manifest_store, "child-1", "validation")
    provenance = build_validation_child_provenance(
        report_id="review-1",
        validation_plan_id="plan-v1",
        source_experiment_id="source-exp",
        review_provenance_checksum="d" * 64,
        child_manifests=(child,),
        expected_target_ids=("validation",),
    )
    with pytest.raises(ValidationChildProvenanceError, match="checksum changed"):
        verify_validation_child_provenance(
            provenance,
            manifest_reader=manifest_store,
            current_review_provenance_checksum="e" * 64,
        )
