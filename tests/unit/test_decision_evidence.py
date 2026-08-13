"""Tests for fail-closed experiment evidence admission into the research decision ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.decision_evidence import (
    VerifiedResearchDecisionLedger,
    audit_decision_evidence,
)
from trade_scout.experiments.decision_ledger import FileResearchDecisionLedger
from trade_scout.experiments.decisions import (
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _Stage:
    @property
    def name(self) -> str:
        return "measure"

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(stage_name=self.name, outputs={"value": 42})


class _FailingStage:
    @property
    def name(self) -> str:
        return "measure"

    def run(self, context: ExperimentContext) -> StageResult:
        raise RuntimeError("synthetic failure")


def _definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="decision_evidence_fixture",
        hypothesis="Synthetic decision evidence hypothesis",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="dataset_v1",
        universe_version="universe_v1",
        code_version="abc123",
        config_schema_version="0.1.0",
        resolved_configuration={"synthetic": True},
    )


def _decision(experiment_id: str, decision_id: str = "decision_1") -> ResearchDecision:
    return ResearchDecision(
        decision_id=decision_id,
        subject_id="subject_1",
        state=ResearchDecisionState.CANDIDATE,
        experiment_ids=(experiment_id,),
        evidence_references=(f"experiment:{experiment_id}",),
        rationale="Synthetic evidence supports continued investigation.",
        decided_by="researcher",
        decided_at="2026-08-13T00:00:00Z",
    )


def _successful_store(tmp_path: Path) -> tuple[FileManifestStore, str]:
    store = FileManifestStore(tmp_path / "runs")
    runner = ExperimentRunner(store, id_factory=lambda: "exp_success")
    manifest = runner.run(_definition(), (_Stage(),))
    return store, manifest.experiment_id


def test_successful_intact_experiment_is_admissible_decision_evidence(tmp_path: Path) -> None:
    store, experiment_id = _successful_store(tmp_path)

    report = audit_decision_evidence(store, _decision(experiment_id))

    assert report.verified
    assert report.experiments[0].admissible
    report.require_verified()


def test_missing_experiment_fails_closed(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path / "runs")

    report = audit_decision_evidence(store, _decision("missing_exp"))

    assert not report.verified
    assert not report.experiments[0].integrity_verified
    with pytest.raises(ResearchDecisionError, match="missing_exp"):
        report.require_verified()


def test_tampered_stage_artifact_is_rejected_before_decision_append(tmp_path: Path) -> None:
    store, experiment_id = _successful_store(tmp_path)
    artifact = tmp_path / "runs" / experiment_id / "artifacts" / "measure.json"
    artifact.write_text('{"value":43}\n', encoding="utf-8")
    ledger = VerifiedResearchDecisionLedger(
        FileResearchDecisionLedger(tmp_path / "decisions"),
        store,
    )

    with pytest.raises(ResearchDecisionError, match="evidence verification failed"):
        ledger.append(_decision(experiment_id))

    assert not (tmp_path / "decisions" / "decision_1.json").exists()


def test_failed_experiment_is_rejected_even_when_manifest_is_intact(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path / "runs")
    runner = ExperimentRunner(store, id_factory=lambda: "exp_failed")
    with pytest.raises(Exception):
        runner.run(_definition(), (_FailingStage(),))

    report = audit_decision_evidence(store, _decision("exp_failed"))

    assert not report.verified
    assert report.experiments[0].integrity_verified
    assert report.experiments[0].status is not None
    assert "FAILED" in report.experiments[0].detail


def test_verified_ledger_appends_and_preserves_authoritative_read_contract(tmp_path: Path) -> None:
    store, experiment_id = _successful_store(tmp_path)
    base_ledger = FileResearchDecisionLedger(tmp_path / "decisions")
    ledger = VerifiedResearchDecisionLedger(base_ledger, store)
    decision = _decision(experiment_id)

    checksum = ledger.append(decision)

    assert checksum
    assert ledger.read(decision.decision_id) == decision
    assert ledger.current(decision.subject_id) == decision
    assert ledger.history(decision.subject_id) == (decision,)
