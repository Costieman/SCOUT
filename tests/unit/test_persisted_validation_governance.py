"""Tests for store-backed validation evidence resolution before research governance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.experiments import (
    PersistedValidationGovernedResearchDecisionLedger,
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
    resolve_persisted_validation_reviews,
    validation_review_reference,
    validation_review_report_id,
)
from trade_scout.validation import (
    EvidenceAssignment,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceTargetKind,
    FileValidationReviewStore,
    MetricEstimate,
    SampleAccounting,
    ValidationCompleteness,
    ValidationEvidenceReport,
    ValidationReviewBundle,
    ValidationRoleCount,
)


def _sample() -> SampleAccounting:
    return SampleAccounting(raw_event_count=50, unique_instrument_count=30, effective_sample_size=25)


def _bundle(
    report_id: str = "validation-001",
    experiment_id: str = "experiment-001",
) -> ValidationReviewBundle:
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
            warnings=("holdout effect is adverse",),
        ),
    )
    return ValidationReviewBundle(
        report=ValidationEvidenceReport(
            report_id=report_id,
            experiment_id=experiment_id,
            validation_plan_id="plan-001",
            primary_outcome="forward_return_60",
            snapshots=snapshots,
        ),
        assignments=(
            EvidenceAssignment(
                "development-evidence", EvidenceTargetKind.SEGMENT, "development"
            ),
            EvidenceAssignment("validation-evidence", EvidenceTargetKind.SEGMENT, "validation"),
            EvidenceAssignment("holdout-evidence", EvidenceTargetKind.SEGMENT, "holdout"),
        ),
        completeness=ValidationCompleteness(
            complete=True,
            missing_targets=(),
            unexpected_targets=(),
            role_mismatches=(),
            unassigned_evidence=(),
        ),
        role_counts=tuple(
            ValidationRoleCount(role, sum(snapshot.role is role for snapshot in snapshots))
            for role in EvidenceRole
        ),
    )


def _decision(
    *,
    evidence_references: tuple[str, ...] = ("validation-review:validation-001",),
    experiment_ids: tuple[str, ...] = ("experiment-001",),
) -> ResearchDecision:
    return ResearchDecision(
        decision_id="decision-001",
        subject_id="subject-001",
        state=ResearchDecisionState.INCONCLUSIVE,
        experiment_ids=experiment_ids,
        evidence_references=evidence_references,
        rationale="The evidence is complete but does not yet justify promotion.",
        decided_by="research-reviewer",
        decided_at="2026-08-13T10:00:00Z",
    )


class _RecordingGovernedLedger:
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


def test_validation_review_report_id_parses_only_canonical_reference() -> None:
    assert validation_review_report_id("validation-review:review-001") == "review-001"
    assert validation_review_report_id("experiment:exp-001") is None

    for reference in (
        "validation-review:",
        "validation-review: review-001",
        "validation-review:review/001",
        "validation-review:..",
    ):
        with pytest.raises(ResearchDecisionError, match="malformed validation review reference"):
            validation_review_report_id(reference)


def test_resolve_persisted_reviews_returns_verified_checksum_and_bundle(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    bundle = _bundle()
    expected_checksum = store.write(bundle)

    resolved = resolve_persisted_validation_reviews(_decision(), store)

    assert len(resolved) == 1
    assert resolved[0].reference == validation_review_reference(bundle)
    assert resolved[0].report_id == bundle.report.report_id
    assert resolved[0].checksum == expected_checksum
    assert resolved[0].bundle == bundle


def test_resolve_persisted_reviews_requires_a_validation_reference(tmp_path: Path) -> None:
    decision = _decision(evidence_references=("experiment-artifact:summary",))

    with pytest.raises(ResearchDecisionError, match="cites no persisted validation review"):
        resolve_persisted_validation_reviews(decision, FileValidationReviewStore(tmp_path))


def test_resolve_persisted_reviews_rejects_missing_review(tmp_path: Path) -> None:
    with pytest.raises(ResearchDecisionError, match="persisted validation review verification failed"):
        resolve_persisted_validation_reviews(_decision(), FileValidationReviewStore(tmp_path))


def test_resolve_persisted_reviews_rejects_duplicate_references(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    decision = _decision(
        evidence_references=(
            "validation-review:validation-001",
            "validation-review:validation-001",
        )
    )

    with pytest.raises(ResearchDecisionError, match="references must be unique"):
        resolve_persisted_validation_reviews(decision, store)


def test_resolve_persisted_reviews_rejects_checksum_tampering(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    path = tmp_path / "validation-001.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["bundle"]["report"]["primary_outcome"] = "tampered-outcome"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ResearchDecisionError, match="checksum mismatch"):
        resolve_persisted_validation_reviews(_decision(), store)


def test_persisted_governance_loads_store_before_delegating(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    bundle = _bundle()
    store.write(bundle)
    recording = _RecordingGovernedLedger()
    ledger = PersistedValidationGovernedResearchDecisionLedger(recording, store)  # type: ignore[arg-type]
    decision = _decision()

    checksum = ledger.append(decision)

    assert checksum == "decision-checksum"
    assert recording.appended == [(decision, (bundle,))]
    assert ledger.read(decision.decision_id) == decision
    assert ledger.current(decision.subject_id) == decision
    assert ledger.history(decision.subject_id) == (decision,)


def test_persisted_governance_never_delegates_when_review_is_corrupt(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    store.write(_bundle())
    path = tmp_path / "validation-001.json"
    path.write_text("{corrupt", encoding="utf-8")
    recording = _RecordingGovernedLedger()
    ledger = PersistedValidationGovernedResearchDecisionLedger(recording, store)  # type: ignore[arg-type]

    with pytest.raises(ResearchDecisionError, match="persisted validation review verification failed"):
        ledger.append(_decision())

    assert recording.appended == []


def test_persisted_governance_preserves_adverse_complete_evidence(tmp_path: Path) -> None:
    store = FileValidationReviewStore(tmp_path)
    bundle = _bundle()
    assert bundle.report.snapshots[-1].metrics[0].estimate < 0
    store.write(bundle)
    recording = _RecordingGovernedLedger()
    ledger = PersistedValidationGovernedResearchDecisionLedger(recording, store)  # type: ignore[arg-type]

    ledger.append(_decision())

    persisted_bundle = recording.appended[0][1][0]
    assert persisted_bundle.report.snapshots[-1].metrics[0].estimate == -0.005
    assert persisted_bundle.report.snapshots[-1].warnings == ("holdout effect is adverse",)
