"""Tests for explicit research decisions and the append-only decision ledger."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trade_scout.experiments.decision_ledger import FileResearchDecisionLedger
from trade_scout.experiments.decisions import (
    ProductionEligibilityAttestation,
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
    validate_decision_supersession,
)


def _decision(
    decision_id: str,
    state: ResearchDecisionState,
    *,
    subject_id: str = "consolidation_breakout_v1",
    supersedes: str | None = None,
    production_attestation: ProductionEligibilityAttestation | None = None,
) -> ResearchDecision:
    return ResearchDecision(
        decision_id=decision_id,
        subject_id=subject_id,
        state=state,
        experiment_ids=("exp_j",),
        evidence_references=("artifacts/exp_j/summary.json",),
        rationale=f"Explicit synthetic decision: {state.value}",
        decided_by="research_review",
        decided_at="2026-08-13T01:00:00+00:00",
        supersedes_decision_id=supersedes,
        production_attestation=production_attestation,
    )


def _complete_attestation() -> ProductionEligibilityAttestation:
    return ProductionEligibilityAttestation(
        implementation_compatible=True,
        cost_assumptions_acceptable=True,
        liquidity_assumptions_acceptable=True,
        risk_policy_validated=True,
        operational_dependencies_available=True,
    )


def test_research_decision_requires_experiment_and_evidence_references() -> None:
    with pytest.raises(ValueError, match="cite at least one experiment"):
        replace(_decision("decision_1", ResearchDecisionState.REJECTED), experiment_ids=())
    with pytest.raises(ValueError, match="evidence artifact"):
        replace(
            _decision("decision_2", ResearchDecisionState.INCONCLUSIVE),
            evidence_references=(),
        )


def test_production_eligible_decision_requires_complete_attestation() -> None:
    with pytest.raises(ValueError, match="complete production attestation"):
        _decision("decision_prod", ResearchDecisionState.PRODUCTION_ELIGIBLE)

    incomplete = replace(_complete_attestation(), risk_policy_validated=False)
    with pytest.raises(ValueError, match="complete production attestation"):
        _decision(
            "decision_prod",
            ResearchDecisionState.PRODUCTION_ELIGIBLE,
            production_attestation=incomplete,
        )


def test_nonproduction_decision_rejects_production_attestation() -> None:
    with pytest.raises(ValueError, match="only valid for PRODUCTION-ELIGIBLE"):
        _decision(
            "decision_candidate",
            ResearchDecisionState.CANDIDATE,
            production_attestation=_complete_attestation(),
        )


def test_production_eligibility_requires_immediately_prior_validated_decision() -> None:
    candidate = _decision("decision_candidate", ResearchDecisionState.CANDIDATE)
    production = _decision(
        "decision_prod",
        ResearchDecisionState.PRODUCTION_ELIGIBLE,
        supersedes=candidate.decision_id,
        production_attestation=_complete_attestation(),
    )
    with pytest.raises(ResearchDecisionError, match="only supersede a VALIDATED"):
        validate_decision_supersession(production, candidate)

    validated = _decision("decision_valid", ResearchDecisionState.VALIDATED)
    production_after_validation = replace(
        production,
        supersedes_decision_id=validated.decision_id,
    )
    validate_decision_supersession(production_after_validation, validated)


def test_first_decision_cannot_claim_production_eligibility() -> None:
    production = _decision(
        "decision_prod",
        ResearchDecisionState.PRODUCTION_ELIGIBLE,
        production_attestation=_complete_attestation(),
    )
    with pytest.raises(ResearchDecisionError, match="requires a prior VALIDATED"):
        validate_decision_supersession(production, None)


def test_ledger_preserves_complete_supersession_history(tmp_path: Path) -> None:
    ledger = FileResearchDecisionLedger(tmp_path / "decisions")
    candidate = _decision("decision_candidate", ResearchDecisionState.CANDIDATE)
    validated = _decision(
        "decision_validated",
        ResearchDecisionState.VALIDATED,
        supersedes=candidate.decision_id,
    )
    production = _decision(
        "decision_production",
        ResearchDecisionState.PRODUCTION_ELIGIBLE,
        supersedes=validated.decision_id,
        production_attestation=_complete_attestation(),
    )

    ledger.append(candidate)
    ledger.append(validated)
    checksum = ledger.append(production)

    assert len(checksum) == 64
    assert ledger.current(candidate.subject_id) == production
    assert tuple(item.state for item in ledger.history(candidate.subject_id)) == (
        ResearchDecisionState.CANDIDATE,
        ResearchDecisionState.VALIDATED,
        ResearchDecisionState.PRODUCTION_ELIGIBLE,
    )
    assert ledger.read("decision_candidate") == candidate


def test_ledger_never_overwrites_existing_decision_id(tmp_path: Path) -> None:
    ledger = FileResearchDecisionLedger(tmp_path / "decisions")
    decision = _decision("decision_1", ResearchDecisionState.INCONCLUSIVE)
    ledger.append(decision)

    with pytest.raises(ResearchDecisionError, match="already exists"):
        ledger.append(decision)


def test_new_subject_decision_cannot_supersede_other_subject(tmp_path: Path) -> None:
    first = _decision("decision_a", ResearchDecisionState.CANDIDATE, subject_id="subject_a")
    crossed = _decision(
        "decision_b",
        ResearchDecisionState.VALIDATED,
        subject_id="subject_b",
        supersedes=first.decision_id,
    )
    with pytest.raises(ResearchDecisionError, match="cross analytical subjects"):
        validate_decision_supersession(crossed, first)


def test_ledger_rejects_tampered_decision_file(tmp_path: Path) -> None:
    ledger = FileResearchDecisionLedger(tmp_path / "decisions")
    decision = _decision("decision_1", ResearchDecisionState.REJECTED)
    ledger.append(decision)
    path = tmp_path / "decisions" / "decision_1.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("REJECTED", "CANDIDATE"), encoding="utf-8")

    with pytest.raises(ResearchDecisionError, match="checksum mismatch"):
        ledger.read("decision_1")


def test_supersession_must_target_current_subject_decision(tmp_path: Path) -> None:
    ledger = FileResearchDecisionLedger(tmp_path / "decisions")
    candidate = _decision("decision_candidate", ResearchDecisionState.CANDIDATE)
    validated = _decision(
        "decision_validated",
        ResearchDecisionState.VALIDATED,
        supersedes=candidate.decision_id,
    )
    ledger.append(candidate)
    ledger.append(validated)

    stale = _decision(
        "decision_stale",
        ResearchDecisionState.INCONCLUSIVE,
        supersedes=candidate.decision_id,
    )
    with pytest.raises(ResearchDecisionError, match="current subject decision"):
        ledger.append(stale)
