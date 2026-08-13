"""Tests for immutable checksum-verified validation review persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.validation import (
    AdjustedPValue,
    ComparatorDefinition,
    ComparatorKind,
    ConfidenceInterval,
    EffectEstimate,
    EvidenceAssignment,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceTargetKind,
    FileValidationReviewStore,
    HypothesisFamily,
    MetricEstimate,
    MultiplicityMethod,
    MultiplicitySummary,
    ParameterAxis,
    ParameterCell,
    ParameterSurface,
    SampleAccounting,
    ValidationCompleteness,
    ValidationEvidenceReport,
    ValidationReviewBundle,
    ValidationReviewStoreError,
    ValidationRoleCount,
)


def _sample() -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=120,
        unique_instrument_count=70,
        effective_sample_size=58.5,
        cluster_count=20,
        exclusions=("missing next-session open",),
    )


def _interval() -> ConfidenceInterval:
    return ConfidenceInterval(lower=0.01, upper=0.05, confidence_level=0.95, method="bootstrap")


def _bundle(report_id: str = "review-001") -> ValidationReviewBundle:
    comparator = ComparatorDefinition(
        comparator_id="trend-matched-v1",
        kind=ComparatorKind.TREND_MATCHED,
        description="Predeclared trend-matched comparator",
        matching_fields=("trend_context", "sector"),
    )
    effect = EffectEstimate(
        effect_id="excess-return",
        metric="forward_return_60",
        estimate=0.018,
        units="fraction",
        comparator=comparator,
        sample=_sample(),
        interval=_interval(),
        p_value=0.02,
        adjusted_p_value=0.04,
    )
    snapshots = (
        EvidenceSnapshot(
            evidence_id="development",
            role=EvidenceRole.DEVELOPMENT,
            sample=_sample(),
            metrics=(MetricEstimate("forward_return_60", 0.025, "fraction", _interval()),),
            effects=(effect,),
        ),
        EvidenceSnapshot(
            evidence_id="validation",
            role=EvidenceRole.VALIDATION,
            sample=_sample(),
            metrics=(MetricEstimate("forward_return_60", 0.021, "fraction", _interval()),),
            effects=(effect,),
            warnings=("effective sample below raw count",),
        ),
        EvidenceSnapshot(
            evidence_id="holdout",
            role=EvidenceRole.FINAL_HOLDOUT,
            sample=_sample(),
            metrics=(MetricEstimate("forward_return_60", 0.019, "fraction", _interval()),),
            effects=(effect,),
        ),
    )
    report = ValidationEvidenceReport(
        report_id=report_id,
        experiment_id="exp-confirmatory-001",
        validation_plan_id="validation-plan-001",
        primary_outcome="forward_return_60",
        snapshots=snapshots,
        multiplicity_family_id="duration-family",
        notes=("Holdout retained for final review.",),
    )
    assignments = (
        EvidenceAssignment("development", EvidenceTargetKind.SEGMENT, "development"),
        EvidenceAssignment("validation", EvidenceTargetKind.SEGMENT, "validation"),
        EvidenceAssignment("holdout", EvidenceTargetKind.SEGMENT, "holdout"),
    )
    completeness = ValidationCompleteness(
        complete=True,
        missing_targets=(),
        unexpected_targets=(),
        role_mismatches=(),
        unassigned_evidence=(),
    )
    role_counts = tuple(
        ValidationRoleCount(role, sum(snapshot.role is role for snapshot in snapshots))
        for role in EvidenceRole
    )
    surface = ParameterSurface(
        surface_id="duration-surface",
        axes=(ParameterAxis("duration", (20, 30)),),
        metric="forward_return_60",
        units="fraction",
        cells=(
            ParameterCell(
                coordinates=(("duration", 20),),
                metric="forward_return_60",
                estimate=0.016,
                units="fraction",
                sample=_sample(),
                interval=_interval(),
            ),
            ParameterCell(
                coordinates=(("duration", 30),),
                metric="forward_return_60",
                estimate=0.019,
                units="fraction",
                sample=_sample(),
                interval=_interval(),
                warnings=("edge cell",),
            ),
        ),
    )
    family = HypothesisFamily(
        family_id="duration-family",
        hypothesis_ids=("duration-20", "duration-30"),
        method=MultiplicityMethod.BONFERRONI,
        alpha=0.05,
    )
    multiplicity = MultiplicitySummary(
        family=family,
        adjusted_values=(
            AdjustedPValue("duration-20", 0.02, 0.04),
            AdjustedPValue("duration-30", 0.03, 0.06),
        ),
    )
    return ValidationReviewBundle(
        report=report,
        assignments=assignments,
        completeness=completeness,
        role_counts=role_counts,
        parameter_surfaces=(surface,),
        multiplicity=(multiplicity,),
        robustness_plan_id="robustness-plan-001",
    )


def _review_path(root: Path, report_id: str = "review-001") -> Path:
    return root / f"{report_id}.json"


def test_store_round_trips_complete_nested_review_bundle(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    bundle = _bundle()

    checksum = store.write(bundle)
    restored = store.read(bundle.report.report_id)

    assert restored == bundle
    assert store.checksum(bundle.report.report_id) == checksum
    assert len(checksum) == 64
    assert store.list_report_ids() == ("review-001",)


def test_store_is_append_only_for_existing_report_id(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())

    with pytest.raises(ValidationReviewStoreError, match="already exists"):
        store.write(_bundle())


def test_store_detects_payload_tampering(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    path = _review_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["bundle"]["report"]["primary_outcome"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidationReviewStoreError, match="checksum mismatch"):
        store.read("review-001")


def test_store_detects_file_identity_tampering_even_with_intact_payload(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    path = _review_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["report_id"] = "other-review"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidationReviewStoreError, match="file identity mismatch"):
        store.read("review-001")


def test_store_rejects_unknown_schema_version(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    path = _review_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = 999
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidationReviewStoreError, match=r"unsupported.*schema"):
        store.read("review-001")


def test_store_rejects_malformed_json(tmp_path: Path) -> None:
    path = _review_path(tmp_path)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValidationReviewStoreError, match="unreadable"):
        FileValidationReviewStore(tmp_path).read("review-001")


def test_store_rejects_missing_review(tmp_path: Path) -> None:
    with pytest.raises(ValidationReviewStoreError, match="not found"):
        FileValidationReviewStore(tmp_path).read("missing")


def test_store_rejects_unsafe_report_ids(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)

    for report_id in ("", "../review", "review/child", "review\\child", " review "):
        with pytest.raises(ValueError, match="report_id"):
            store.read(report_id)


def test_list_report_ids_is_sorted_and_does_not_parse_contents(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle("z-review"))
    store.write(_bundle("a-review"))
    _review_path(tmp_path, "z-review").write_text("corrupted", encoding="utf-8")

    assert store.list_report_ids() == ("a-review", "z-review")


def test_store_revalidates_nested_domain_invariants_after_checksum_verification(
    tmp_path: Path,
) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    path = _review_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["bundle"]["completeness"]["complete"] = False
    raw["checksum"] = _payload_checksum(raw["bundle"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidationReviewStoreError, match="payload is invalid"):
        store.read("review-001")


def _payload_checksum(payload: object) -> str:
    import hashlib

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
