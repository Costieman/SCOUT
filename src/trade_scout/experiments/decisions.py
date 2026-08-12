"""Explicit research-result decisions and promotion-governance contracts.

Trade Scout may record a scientific decision, but this module never infers one from performance
metrics. Promotion remains an explicit, attributable act backed by cited experiment evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ResearchDecisionState(StrEnum):
    """Research output states defined by the first research-program specification."""

    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    PRODUCTION_ELIGIBLE = "PRODUCTION-ELIGIBLE"


@dataclass(frozen=True, slots=True)
class ProductionEligibilityAttestation:
    """Explicit operational/risk checks required before production eligibility is recorded."""

    implementation_compatible: bool
    cost_assumptions_acceptable: bool
    liquidity_assumptions_acceptable: bool
    risk_policy_validated: bool
    operational_dependencies_available: bool

    @property
    def complete(self) -> bool:
        """Return true only when every declared production prerequisite is affirmed."""

        return all(
            (
                self.implementation_compatible,
                self.cost_assumptions_acceptable,
                self.liquidity_assumptions_acceptable,
                self.risk_policy_validated,
                self.operational_dependencies_available,
            )
        )


@dataclass(frozen=True, slots=True)
class ResearchDecision:
    """Immutable, attributable decision about one tested analytical definition."""

    decision_id: str
    subject_id: str
    state: ResearchDecisionState
    experiment_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    rationale: str
    decided_by: str
    decided_at: str
    supersedes_decision_id: str | None = None
    production_attestation: ProductionEligibilityAttestation | None = None

    def __post_init__(self) -> None:
        required = {
            "decision_id": self.decision_id,
            "subject_id": self.subject_id,
            "rationale": self.rationale,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }
        empty = tuple(name for name, value in required.items() if not value.strip())
        if empty:
            raise ValueError(f"research decision has empty required fields: {', '.join(empty)}")
        if not self.experiment_ids:
            raise ValueError("research decision must cite at least one experiment")
        if any(not item.strip() for item in self.experiment_ids):
            raise ValueError("research decision experiment IDs must be non-empty")
        if len(set(self.experiment_ids)) != len(self.experiment_ids):
            raise ValueError("research decision experiment IDs must be unique")
        if not self.evidence_references:
            raise ValueError("research decision must cite at least one evidence artifact")
        if any(not item.strip() for item in self.evidence_references):
            raise ValueError("research decision evidence references must be non-empty")
        if self.state is ResearchDecisionState.PRODUCTION_ELIGIBLE:
            if self.production_attestation is None or not self.production_attestation.complete:
                raise ValueError(
                    "production-eligible decision requires a complete production attestation"
                )
        elif self.production_attestation is not None:
            raise ValueError("production attestation is only valid for PRODUCTION-ELIGIBLE decisions")


class ResearchDecisionError(RuntimeError):
    """Raised when a decision would violate explicit research-promotion governance."""


def validate_decision_supersession(
    decision: ResearchDecision,
    prior: ResearchDecision | None,
) -> None:
    """Validate lineage without deciding whether the scientific conclusion is justified.

    The first decision for a subject must not claim to supersede anything. Later decisions must
    explicitly supersede the current decision for the same subject. Promotion to PRODUCTION-ELIGIBLE
    requires the immediately prior state to be VALIDATED; all other changes remain explicit research
    decisions and are not automatically inferred by this module.
    """

    if prior is None:
        if decision.supersedes_decision_id is not None:
            raise ResearchDecisionError("first subject decision cannot supersede another decision")
        if decision.state is ResearchDecisionState.PRODUCTION_ELIGIBLE:
            raise ResearchDecisionError(
                "production eligibility requires a prior VALIDATED research decision"
            )
        return

    if prior.subject_id != decision.subject_id:
        raise ResearchDecisionError("decision supersession cannot cross analytical subjects")
    if decision.supersedes_decision_id != prior.decision_id:
        raise ResearchDecisionError("new decision must explicitly supersede the current subject decision")
    if decision.decision_id == prior.decision_id:
        raise ResearchDecisionError("decision ID must change when a decision is superseded")
    if (
        decision.state is ResearchDecisionState.PRODUCTION_ELIGIBLE
        and prior.state is not ResearchDecisionState.VALIDATED
    ):
        raise ResearchDecisionError(
            "production eligibility may only supersede a VALIDATED research decision"
        )
