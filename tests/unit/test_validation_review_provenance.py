"""Tests for cryptographic validation-review provenance binding."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from trade_scout.experiments import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    FileValidationReviewProvenanceStore,
    ResearchMode,
    StageArtifactProvenance,
    ValidationReviewProvenanceError,
    build_validation_review_provenance,
    verify_validation_review_provenance,
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
from trade_scout.validation.store import ValidationReviewStoreError


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


def _sample() -> SampleAccounting:
    return SampleAccounting(raw_event_count=50, unique_instrument_count=30)


def _bundle() -> ValidationReviewBundle:
    snapshots = (
        EvidenceSnapshot(
            evidence_id="development-evidence",
            role=EvidenceRole.DEVELOPMENT,
            sample=_sample(),
            metrics=(MetricEstimate("forward_return_60", 0.02, "fraction"),),
        ),
        EvidenceSnapshot(
            evidence_id="validation-evidence",
            role=EvidenceRole.VALIDATION,
            sample=_sample(),
            metrics=(MetricEstimate("forward_return_60", 0.01, "fraction"),),
        ),
        EvidenceSnapshot(
            evidence_id="holdout-evidence",
            role=EvidenceRole.FINAL_HOLDOUT,
            sample=_sample(),
            metrics=(MetricEstimate("forward_return_60", -0.005, "fraction"),),
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
            name="consolidation breakout confirmation",
            hypothesis="Frozen breakout definition has non-zero forward return.",
            mode=ResearchMode.CONFIRMATORY,
            dataset_version="dataset-v1",
            universe_version="universe-v1",
            code_version="abc123",
            config_schema_version="1",
            resolved_configuration={"window": 60},
        ),
        status=ExperimentStatus.SUCCEEDED,
        created_at="2026-08-13T00:00:00Z",
        completed_at="2026-08-13T01:00:00Z",
        stages=(
            StageRecord(
                stage_name="event_generation",
                started_at="2026-08-13T00:10:00Z",
                completed_at="2026-08-13T00:20:00Z",
                output_checksum="1" * 64,
                warnings=(),
            ),
            StageRecord(
                stage_name="outcome_estimation",
                started_at="2026-08-13T00:20:00Z",
                completed_at="2026-08-13T00:30:00Z",
                output_checksum="2" * 64,
                warnings=(),
            ),
        ),
    )
    return replace(manifest, manifest_checksum=sha256_json(manifest))


def _persisted_review(tmp_path: Path) -> tuple[FileValidationReviewStore, str]:
    store = FileValidationReviewStore(tmp_path / "reviews")
    checksum = store.write(_bundle())
    return store, checksum


def test_build_provenance_binds_review_plan_manifest_and_stage_artifacts(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    provenance = build_validation_review_provenance(
        bundle=review_store.read("review-001"),
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )

    assert provenance.review_checksum == review_checksum
    assert provenance.validation_plan_id == "plan-001"
    assert provenance.experiment_manifest_checksum == _manifest().manifest_checksum
    assert provenance.stage_artifacts == (
        StageArtifactProvenance("event_generation", "1" * 64),
        StageArtifactProvenance("outcome_estimation", "2" * 64),
    )


def test_provenance_store_round_trips_and_detects_tampering(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    provenance = build_validation_review_provenance(
        bundle=review_store.read("review-001"),
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )
    store = FileValidationReviewProvenanceStore(tmp_path / "provenance")
    checksum = store.write(provenance)

    assert store.read("review-001") == provenance
    assert store.checksum("review-001") == checksum

    path = tmp_path / "provenance" / "review-001.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["provenance"]["validation_plan_id"] = "tampered-plan"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationReviewProvenanceError, match="checksum mismatch"):
        store.read("review-001")


def test_provenance_store_is_append_only(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    provenance = build_validation_review_provenance(
        bundle=review_store.read("review-001"),
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )
    store = FileValidationReviewProvenanceStore(tmp_path / "provenance")
    store.write(provenance)

    with pytest.raises(ValidationReviewProvenanceError, match="already exists"):
        store.write(provenance)


def test_build_rejects_manifest_checksum_mismatch(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    manifest = replace(_manifest(), completed_at="2026-08-13T02:00:00Z")

    with pytest.raises(ValidationReviewProvenanceError, match="manifest checksum mismatch"):
        build_validation_review_provenance(
            bundle=review_store.read("review-001"),
            review_checksum=review_checksum,
            plan=_plan(),
            experiment_manifest=manifest,
        )


def test_build_rejects_non_succeeded_source_experiment(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    manifest = replace(_manifest(), status=ExperimentStatus.FAILED, manifest_checksum=None)
    manifest = replace(manifest, manifest_checksum=sha256_json(manifest))

    with pytest.raises(ValidationReviewProvenanceError, match="must be SUCCEEDED"):
        build_validation_review_provenance(
            bundle=review_store.read("review-001"),
            review_checksum=review_checksum,
            plan=_plan(),
            experiment_manifest=manifest,
        )


def test_verify_rejects_changed_validation_design(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    provenance = build_validation_review_provenance(
        bundle=review_store.read("review-001"),
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )
    changed_plan = replace(_plan(), notes=("post hoc note changes frozen design identity",))

    with pytest.raises(ValidationReviewProvenanceError, match="binding mismatch"):
        verify_validation_review_provenance(
            provenance,
            review_store=review_store,
            plan=changed_plan,
            experiment_manifest=_manifest(),
        )


def test_verify_rejects_changed_stage_evidence_identity(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    provenance = build_validation_review_provenance(
        bundle=review_store.read("review-001"),
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )
    manifest = _manifest()
    changed_stage = replace(manifest.stages[0], output_checksum="3" * 64)
    changed_manifest = replace(
        manifest, stages=(changed_stage, manifest.stages[1]), manifest_checksum=None
    )
    changed_manifest = replace(
        changed_manifest,
        manifest_checksum=sha256_json(changed_manifest),
    )

    with pytest.raises(ValidationReviewProvenanceError, match="binding mismatch"):
        verify_validation_review_provenance(
            provenance,
            review_store=review_store,
            plan=_plan(),
            experiment_manifest=changed_manifest,
        )


def test_verify_detects_persisted_review_replacement(tmp_path: Path) -> None:
    review_store, review_checksum = _persisted_review(tmp_path)
    provenance = build_validation_review_provenance(
        bundle=review_store.read("review-001"),
        review_checksum=review_checksum,
        plan=_plan(),
        experiment_manifest=_manifest(),
    )
    path = tmp_path / "reviews" / "review-001.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["bundle"]["report"]["primary_outcome"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidationReviewStoreError, match="checksum mismatch"):
        verify_validation_review_provenance(
            provenance,
            review_store=review_store,
            plan=_plan(),
            experiment_manifest=_manifest(),
        )
