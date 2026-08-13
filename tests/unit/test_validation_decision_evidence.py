"""Tests for explicit validation-review evidence binding in research governance."""

from datetime import date

import pytest

from trade_scout.experiments import (
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
    ValidationDecisionEvidenceReport,
    audit_validation_decision_evidence,
    validation_review_reference,
)
from trade_scout.validation import (
    DateInterval,
    EvidenceAssignment,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceTargetKind,
    MetricEstimate,
    SampleAccounting,
    ValidationEvidenceReport,
    assemble_validation_review_bundle,
    build_fixed_holdout_plan,
)


def _sample() -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=120,
        unique_instrument_count=70,
        effective_sample_size=62.0,
    )


def _plan():
    return build_fixed_holdout_plan(
        plan_id="validation-plan-v1",
        development=DateInterval(date(2000, 1, 1), date(2010, 12, 31)),
        validation=DateInterval(date(2011, 1, 1), date(2018, 12, 31)),
        holdout=DateInterval(date(2019, 1, 1), date(2025, 12, 31)),
        primary_outcome="forward_return_60",
    )


def _snapshot(evidence_id: str, role: EvidenceRole) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        evidence_id=evidence_id,
        role=role,
        sample=_sample(),
        metrics=(MetricEstimate("forward_return_60", 0.02, "fraction"),),
    )


def _bundle(*, report_id: str = "review-001", experiment_id: str = "exp-001"):
    plan = _plan()
    report = ValidationEvidenceReport(
        report_id=report_id,
        experiment_id=experiment_id,
        validation_plan_id=plan.plan_id,
        primary_outcome="forward_return_60",
        snapshots=(
            _snapshot("development", EvidenceRole.DEVELOPMENT),
            _snapshot("validation", EvidenceRole.VALIDATION),
            _snapshot("holdout", EvidenceRole.FINAL_HOLDOUT),
        ),
    )
    assignments = (
        EvidenceAssignment("development", EvidenceTargetKind.SEGMENT, "development"),
        EvidenceAssignment("validation", EvidenceTargetKind.SEGMENT, "validation"),
        EvidenceAssignment("holdout", EvidenceTargetKind.SEGMENT, "holdout"),
    )
    return assemble_validation_review_bundle(
        plan=plan,
        report=report,
        assignments=assignments,
    )


def _decision(
    *,
    experiment_ids: tuple[str, ...] = ("exp-001",),
    evidence_references: tuple[str, ...] = ("validation-review:review-001",),
) -> ResearchDecision:
    return ResearchDecision(
        decision_id="decision-001",
        subject_id="consolidation-breakout-v0.1",
        state=ResearchDecisionState.INCONCLUSIVE,
        experiment_ids=experiment_ids,
        evidence_references=evidence_references,
        rationale="Evidence has been reviewed; no automatic scientific conclusion is inferred.",
        decided_by="research-reviewer",
        decided_at="2026-08-13T18:00:00+08:00",
    )


def test_complete_review_explicitly_cited_by_decision_is_verified() -> None:
    bundle = _bundle()
    report = audit_validation_decision_evidence(_decision(), (bundle,))

    assert report.verified
    assert report.unresolved_references == ()
    assert len(report.reviews) == 1
    review = report.reviews[0]
    assert review.admissible
    assert review.report_id == "review-001"
    assert review.experiment_id == "exp-001"
    assert review.evidence_count == 3
    assert review.warning_count == 0
    assert review.validation_plan_id == "validation-plan-v1"


def test_validation_review_reference_is_canonical_and_deterministic() -> None:
    bundle = _bundle(report_id="review-alpha")

    assert validation_review_reference(bundle) == "validation-review:review-alpha"
    assert validation_review_reference(bundle) == validation_review_reference(bundle)


def test_review_must_be_explicitly_named_in_decision_evidence_references() -> None:
    bundle = _bundle()
    decision = _decision(evidence_references=("artifact:some-other-report",))
    report = audit_validation_decision_evidence(decision, (bundle,))

    assert not report.verified
    assert not report.reviews[0].reference_cited
    with pytest.raises(ResearchDecisionError, match="is not cited by decision"):
        report.require_verified()


def test_review_experiment_must_also_be_cited_by_decision() -> None:
    bundle = _bundle(experiment_id="exp-002")
    decision = _decision(experiment_ids=("exp-001",))
    report = audit_validation_decision_evidence(decision, (bundle,))

    assert not report.verified
    assert not report.reviews[0].experiment_cited
    with pytest.raises(ResearchDecisionError, match="exp-002"):
        report.require_verified()


def test_unresolved_validation_review_reference_fails_closed() -> None:
    bundle = _bundle()
    decision = _decision(
        evidence_references=(
            "validation-review:review-001",
            "validation-review:missing-review",
        )
    )
    report = audit_validation_decision_evidence(decision, (bundle,))

    assert not report.verified
    assert report.unresolved_references == ("validation-review:missing-review",)
    with pytest.raises(ResearchDecisionError, match="unresolved references"):
        report.require_verified()


def test_supplying_no_validation_review_fails_closed() -> None:
    report = audit_validation_decision_evidence(_decision(), ())

    assert not report.verified
    with pytest.raises(ResearchDecisionError, match="no validation review bundles supplied"):
        report.require_verified()


def test_duplicate_review_report_ids_are_rejected() -> None:
    first = _bundle(report_id="review-duplicate", experiment_id="exp-001")
    second = _bundle(report_id="review-duplicate", experiment_id="exp-002")

    with pytest.raises(ValueError, match="report IDs must be unique"):
        audit_validation_decision_evidence(_decision(), (first, second))


def test_duplicate_validation_review_references_in_decision_are_rejected() -> None:
    bundle = _bundle()
    decision = _decision(
        evidence_references=(
            "validation-review:review-001",
            "validation-review:review-001",
        )
    )

    with pytest.raises(ValueError, match="references must be unique"):
        audit_validation_decision_evidence(decision, (bundle,))


def test_report_requires_at_least_one_admissible_review_to_verify() -> None:
    report = ValidationDecisionEvidenceReport(decision_id="decision-empty", reviews=())

    assert not report.verified
