"""Tests for mandatory validation provenance at the research-decision boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from trade_scout.experiments import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    FileValidationReviewProvenanceStore,
    ProvenanceGovernedResearchDecisionLedger,
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
    ResearchMode,
    build_validation_review_provenance,
    resolve_provenance_verified_validation_reviews,
)
from trade_scout.experiments.contracts import StageRecord
from trade_scout.experiments.serialization import sha256_json
from trade_scout.validation import (
    DateInterval,
    EvidenceAssignment,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceTargetKind,
    FileValidationReviewStore,
    MetricEstimate,
    SampleAccounting,
    ValidationCompleteness,
    ValidationEvidenceReport,
    ValidationPlan,
    ValidationReviewBundle,
    ValidationRole,
    ValidationRoleCount,
    ValidationSegment,
)


def _plan() -> ValidationPlan:
    return ValidationPlan(
        plan_id="plan-001",
        segments=(
            ValidationSegment(
                "development",
                ValidationRole.DEVELOPMENT,
                DateInterval(date(2018, 1, 1), date(2020, 12, 31)),
            ),
            ValidationSegment(
                "validation",
                ValidationRole.VALIDATION,
                DateInterval(date(2021, 1, 1), date(2022, 12, 31)),
            ),
            ValidationSegment(
                "holdout",
                ValidationRole.HOLDOUT,
                DateInterval(date(2023, 1, 1), date(2024, 12, 31)),
            ),
        ),
        primary_outcome="forward_return_60",
    )


def _bundle() -> ValidationReviewBundle:
    sample = SampleAccounting(raw_event_count=40, unique_instrument_count=25)
    snapshots = (
        EvidenceSnapshot(
            "development-evidence",
            EvidenceRole.DEVELOPMENT,
            sample,
            (MetricEstimate("forward_return_60", 0.02, "fraction"),),
        ),
        EvidenceSnapshot(
            "validation-evidence",
            EvidenceRole.VALIDATION,
            sample,
            (MetricEstimate("forward_return_60", 0.01, "fraction"),),
        ),
        EvidenceSnapshot(
            "holdout-evidence",
            EvidenceRole.FINAL_HOLDOUT,
            sample,
            (MetricEstimate("forward_return_60", -0.004, "fraction"),),
        ),
    )
    return ValidationReviewBundle(
        report=ValidationEvidenceReport(
            report_id="review-001",
            experiment_id="experiment-001",
            validation_plan_id="plan-001",
            primary_outcome="forward_return_60",
            snapshots=snapshots,
        ),
        assignments=(
            EvidenceAssignment("development-evidence", EvidenceTargetKind.SEGMENT, "development"),
            EvidenceAssignment("validation-evidence", EvidenceTargetKind.SEGMENT, "validation"),
            EvidenceAssignment("holdout-evidence", EvidenceTargetKind.SEGMENT, "holdout"),
        ),
        completeness=ValidationCompleteness(True, (), (), (), ()),
        role_counts=tuple(
            ValidationRoleCount(role, sum(snapshot.role is role for snapshot in snapshots))
            for role in EvidenceRole
        ),
    )


def _manifest() -> ExperimentManifest:
    manifest = ExperimentManifest(
        experiment_id="experiment-001",
        definition=ExperimentDefinition(
            name="confirmatory breakout",
            hypothesis="Frozen rule has non-zero forward return.",
            mode=ResearchMode.CONFIRMATORY,
            dataset_version="dataset-v1",
            universe_version="universe-v1",
            code_version="abc123",
            config_schema_version="1",
            resolved_configuration={"horizon": 60},
        ),
        status=ExperimentStatus.SUCCEEDED,
        created_at="2026-08-13T00:00:00Z",
        completed_at="2026-08-13T01:00:00Z",
        stages=(
            StageRecord(
                "event_generation",
                "2026-08-13T00:10:00Z",
                "2026-08-13T00:20:00Z",
                "1" * 64,
                (),
            ),
            StageRecord(
                "outcome_estimation",
                "2026-08-13T00:20:00Z",
                "2026-08-13T00:30:00Z",
                "2" * 64,
                (),
            ),
        ),
    )
    return replace(manifest, manifest_checksum=sha256_json(manifest))


def _decision() -> ResearchDecision:
    return ResearchDecision(
        decision_id="decision-001",
        subject_id="subject-001",
        state=ResearchDecisionState.INCONCLUSIVE,
        experiment_ids=("experiment-001",),
        evidence_references=("validation-review:review-001",),
        rationale="Complete evidence is retained without automatic promotion.",
        decided_by="research-reviewer",
        decided_at="2026-08-13T10:00:00Z",
    )


class _PlanReader:
    def __init__(self, plan: ValidationPlan) -> None:
        self.plan = plan

    def read_validation_plan(self, plan_id: str) -> ValidationPlan:
        if plan_id != self.plan.plan_id:
            raise KeyError(plan_id)
        return self.plan


class _ManifestReader:
    def __init__(self, manifest: ExperimentManifest) -> None:
        self.manifest = manifest

    def read_manifest(self, experiment_id: str) -> ExperimentManifest:
        if experiment_id != self.manifest.experiment_id:
            raise KeyError(experiment_id)
        return self.manifest


class _RecordingValidationLedger:
    def __init__(self) -> None:
        self.appended: list[tuple[ResearchDecision, tuple[ValidationReviewBundle, ...]]] = []

    def append(
        self,
        decision: ResearchDecision,
        *,
        validation_reviews: tuple[ValidationReviewBundle, ...],
    ) -> str:
        self.appended.append((decision, validation_reviews))
        return "decision-checksum"

    def read(self, decision_id: str) -> ResearchDecision:
        if not self.appended or self.appended[-1][0].decision_id != decision_id:
            raise KeyError(decision_id)
        return self.appended[-1][0]

    def history(self, subject_id: str) -> tuple[ResearchDecision, ...]:
        return tuple(item[0] for item in self.appended if item[0].subject_id == subject_id)

    def current(self, subject_id: str) -> ResearchDecision | None:
        history = self.history(subject_id)
        return history[-1] if history else None


def _stores(
    tmp_path: Path,
) -> tuple[FileValidationReviewStore, FileValidationReviewProvenanceStore]:
    review_store = FileValidationReviewStore(tmp_path / "reviews")
    bundle = _bundle()
    review_checksum = review_store.write(bundle)
    provenance = build_validation_review_provenance(
        bundle=bundle,
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )
    provenance_store = FileValidationReviewProvenanceStore(tmp_path / "provenance")
    provenance_store.write(provenance)
    return review_store, provenance_store


def test_resolver_requires_and_reproduces_persisted_provenance(tmp_path: Path) -> None:
    review_store, provenance_store = _stores(tmp_path)

    verified = resolve_provenance_verified_validation_reviews(
        _decision(),
        review_store=review_store,
        provenance_store=provenance_store,
        validation_plan_reader=_PlanReader(_plan()),
        experiment_manifest_reader=_ManifestReader(_manifest()),
    )

    assert len(verified) == 1
    item = verified[0]
    assert item.report_id == "review-001"
    assert item.validation_plan_id == "plan-001"
    assert item.experiment_id == "experiment-001"
    assert item.bundle == _bundle()
    assert item.review_checksum == review_store.checksum("review-001")
    assert item.provenance_checksum == provenance_store.checksum("review-001")


def test_governed_ledger_verifies_provenance_before_delegating(tmp_path: Path) -> None:
    review_store, provenance_store = _stores(tmp_path)
    recording = _RecordingValidationLedger()
    ledger = ProvenanceGovernedResearchDecisionLedger(
        recording,  # type: ignore[arg-type]
        review_store=review_store,
        provenance_store=provenance_store,
        validation_plan_reader=_PlanReader(_plan()),
        experiment_manifest_reader=_ManifestReader(_manifest()),
    )

    checksum = ledger.append(_decision())

    assert checksum == "decision-checksum"
    assert recording.appended == [(_decision(), (_bundle(),))]
    assert ledger.current("subject-001") == _decision()
    assert ledger.history("subject-001") == (_decision(),)


def test_missing_provenance_fails_before_decision_mutation(tmp_path: Path) -> None:
    review_store = FileValidationReviewStore(tmp_path / "reviews")
    review_store.write(_bundle())
    recording = _RecordingValidationLedger()
    ledger = ProvenanceGovernedResearchDecisionLedger(
        recording,  # type: ignore[arg-type]
        review_store=review_store,
        provenance_store=FileValidationReviewProvenanceStore(tmp_path / "provenance"),
        validation_plan_reader=_PlanReader(_plan()),
        experiment_manifest_reader=_ManifestReader(_manifest()),
    )

    with pytest.raises(ResearchDecisionError, match="provenance verification failed"):
        ledger.append(_decision())

    assert recording.appended == []


def test_changed_validation_plan_fails_before_decision_mutation(tmp_path: Path) -> None:
    review_store, provenance_store = _stores(tmp_path)
    changed_plan = replace(_plan(), notes=("post hoc change",))
    recording = _RecordingValidationLedger()
    ledger = ProvenanceGovernedResearchDecisionLedger(
        recording,  # type: ignore[arg-type]
        review_store=review_store,
        provenance_store=provenance_store,
        validation_plan_reader=_PlanReader(changed_plan),
        experiment_manifest_reader=_ManifestReader(_manifest()),
    )

    with pytest.raises(ResearchDecisionError, match="binding mismatch"):
        ledger.append(_decision())

    assert recording.appended == []


def test_changed_source_stage_identity_fails_before_decision_mutation(tmp_path: Path) -> None:
    review_store, provenance_store = _stores(tmp_path)
    manifest = _manifest()
    changed_stage = replace(manifest.stages[0], output_checksum="3" * 64)
    changed_manifest = replace(
        manifest,
        stages=(changed_stage, manifest.stages[1]),
        manifest_checksum=None,
    )
    changed_manifest = replace(
        changed_manifest,
        manifest_checksum=sha256_json(changed_manifest),
    )
    recording = _RecordingValidationLedger()
    ledger = ProvenanceGovernedResearchDecisionLedger(
        recording,  # type: ignore[arg-type]
        review_store=review_store,
        provenance_store=provenance_store,
        validation_plan_reader=_PlanReader(_plan()),
        experiment_manifest_reader=_ManifestReader(changed_manifest),
    )

    with pytest.raises(ResearchDecisionError, match="binding mismatch"):
        ledger.append(_decision())

    assert recording.appended == []


def test_review_replacement_fails_before_decision_mutation(tmp_path: Path) -> None:
    review_store, provenance_store = _stores(tmp_path)
    path = tmp_path / "reviews" / "review-001.json"
    raw = path.read_text(encoding="utf-8").replace("forward_return_60", "tampered_metric", 1)
    path.write_text(raw, encoding="utf-8")
    recording = _RecordingValidationLedger()
    ledger = ProvenanceGovernedResearchDecisionLedger(
        recording,  # type: ignore[arg-type]
        review_store=review_store,
        provenance_store=provenance_store,
        validation_plan_reader=_PlanReader(_plan()),
        experiment_manifest_reader=_ManifestReader(_manifest()),
    )

    with pytest.raises(
        ResearchDecisionError, match="persisted validation review verification failed"
    ):
        ledger.append(_decision())

    assert recording.appended == []
