"""Tests for validation child-experiment provenance bindings."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trade_scout.experiments.contracts import ExperimentContext, ExperimentDefinition, ResearchMode, StageResult
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.validation_child_provenance import ValidationChildProvenanceError, build_validation_child_provenance


class _Stage:
    name = "estimate"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(self.name, {"estimate": 0.01})


def _definition(parent: str, target_id: str) -> ExperimentDefinition:
    return ExperimentDefinition(name="validation child", hypothesis="Frozen validation execution.", mode=ResearchMode.CONFIRMATORY, dataset_version="dataset-v1", universe_version="universe-v1", code_version="code-v1", config_schema_version="1", resolved_configuration={"_validation_target": {"validation_plan_id": "plan-v1", "target_id": target_id}}, parent_experiment_id=parent)


def test_rejects_parent_lineage_drift(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    child = ExperimentRunner(store, id_factory=lambda: "child-1").run(_definition("source-exp", "validation"), (_Stage(),))
    wrong_parent = replace(child, definition=replace(child.definition, parent_experiment_id="other"))
    with pytest.raises(ValidationChildProvenanceError, match="parent lineage"):
        build_validation_child_provenance(report_id="review-1", validation_plan_id="plan-v1", source_experiment_id="source-exp", review_provenance_checksum="a" * 64, child_manifests=(wrong_parent,), expected_target_ids=("validation",))
