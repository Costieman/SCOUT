"""Typed statistical-evidence records for validation and research reporting.

These contracts preserve estimates, uncertainty, comparator identity, sample accounting, and
validation context. They deliberately do not decide whether a strategy should be promoted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from trade_scout.validation.contracts import SampleAccounting


class ComparatorKind(StrEnum):
    """Registered comparison populations supported by the first research program."""

    UNCONDITIONAL = "UNCONDITIONAL"
    TREND_MATCHED = "TREND_MATCHED"
    REGIME_MATCHED = "REGIME_MATCHED"
    SECTOR_MATCHED = "SECTOR_MATCHED"
    RANDOMIZED_PSEUDO_EVENT = "RANDOMIZED_PSEUDO_EVENT"
    SIMPLE_EVENT_BASELINE = "SIMPLE_EVENT_BASELINE"


@dataclass(frozen=True, slots=True)
class ComparatorDefinition:
    """Immutable definition of the population against which an effect is measured."""

    comparator_id: str
    kind: ComparatorKind
    description: str
    matching_fields: tuple[str, ...] = ()
    random_seed: int | None = None

    def __post_init__(self) -> None:
        if not self.comparator_id.strip():
            raise ValueError("comparator_id must be non-empty")
        if not self.description.strip():
            raise ValueError("comparator description must be non-empty")
        if any(not field.strip() for field in self.matching_fields):
            raise ValueError("comparator matching fields must be non-empty")
        if len(set(self.matching_fields)) != len(self.matching_fields):
            raise ValueError("comparator matching fields must be unique")
        randomized = self.kind is ComparatorKind.RANDOMIZED_PSEUDO_EVENT
        if randomized and self.random_seed is None:
            raise ValueError("randomized pseudo-event comparators require a recorded seed")
        if not randomized and self.random_seed is not None:
            raise ValueError("random_seed is reserved for randomized pseudo-event comparators")


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    """Two-sided uncertainty interval attached to one reported estimate."""

    lower: float
    upper: float
    confidence_level: float
    method: str

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.lower, self.upper, self.confidence_level)):
            raise ValueError("confidence interval values must be finite")
        if self.lower > self.upper:
            raise ValueError("confidence interval lower bound cannot exceed upper bound")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must lie strictly between zero and one")
        if not self.method.strip():
            raise ValueError("confidence interval method must be non-empty")


@dataclass(frozen=True, slots=True)
class MetricEstimate:
    """One named metric estimate with units and optional uncertainty interval."""

    metric: str
    estimate: float
    units: str
    interval: ConfidenceInterval | None = None

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric name must be non-empty")
        if not isfinite(self.estimate):
            raise ValueError("metric estimate must be finite")
        if not self.units.strip():
            raise ValueError("metric units must be non-empty")


@dataclass(frozen=True, slots=True)
class EffectEstimate:
    """Difference between a fixed research cohort and a predeclared comparator."""

    effect_id: str
    metric: str
    estimate: float
    units: str
    comparator: ComparatorDefinition
    sample: SampleAccounting
    interval: ConfidenceInterval | None = None
    p_value: float | None = None
    adjusted_p_value: float | None = None

    def __post_init__(self) -> None:
        if not self.effect_id.strip():
            raise ValueError("effect_id must be non-empty")
        if not self.metric.strip():
            raise ValueError("effect metric must be non-empty")
        if not self.units.strip():
            raise ValueError("effect units must be non-empty")
        if not isfinite(self.estimate):
            raise ValueError("effect estimate must be finite")
        for field_name, value in (
            ("p_value", self.p_value),
            ("adjusted_p_value", self.adjusted_p_value),
        ):
            if value is not None and (not isfinite(value) or not 0.0 <= value <= 1.0):
                raise ValueError(f"{field_name} must be finite and between zero and one")
        if self.adjusted_p_value is not None and self.p_value is None:
            raise ValueError("adjusted_p_value requires an unadjusted p_value")


class EvidenceRole(StrEnum):
    """Context in which one evidence record was generated."""

    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    WALK_FORWARD = "WALK_FORWARD"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"
    ROBUSTNESS = "ROBUSTNESS"


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    """Complete descriptive evidence for one frozen cohort and evaluation context."""

    evidence_id: str
    role: EvidenceRole
    sample: SampleAccounting
    metrics: tuple[MetricEstimate, ...]
    effects: tuple[EffectEstimate, ...] = ()
    fold_id: str | None = None
    challenge_id: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must be non-empty")
        if not self.metrics:
            raise ValueError("evidence snapshot must contain at least one metric")
        metric_names = [metric.metric for metric in self.metrics]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("evidence metric names must be unique")
        effect_ids = [effect.effect_id for effect in self.effects]
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("evidence effect IDs must be unique")
        if self.role is EvidenceRole.WALK_FORWARD and not self.fold_id:
            raise ValueError("walk-forward evidence requires fold_id")
        if self.role is not EvidenceRole.WALK_FORWARD and self.fold_id is not None:
            raise ValueError("fold_id is only valid for walk-forward evidence")
        if self.role is EvidenceRole.ROBUSTNESS and not self.challenge_id:
            raise ValueError("robustness evidence requires challenge_id")
        if self.role is not EvidenceRole.ROBUSTNESS and self.challenge_id is not None:
            raise ValueError("challenge_id is only valid for robustness evidence")
        if any(not warning.strip() for warning in self.warnings):
            raise ValueError("evidence warnings must be non-empty")


@dataclass(frozen=True, slots=True)
class ValidationEvidenceReport:
    """Auditable evidence bundle produced for a frozen validation design.

    The report intentionally contains no automatic promotion decision. Scientific status remains a
    separate governance record in the research decision ledger.
    """

    report_id: str
    experiment_id: str
    validation_plan_id: str
    primary_outcome: str
    snapshots: tuple[EvidenceSnapshot, ...]
    multiplicity_family_id: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("report_id", self.report_id),
            ("experiment_id", self.experiment_id),
            ("validation_plan_id", self.validation_plan_id),
            ("primary_outcome", self.primary_outcome),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if not self.snapshots:
            raise ValueError("validation evidence report must contain at least one snapshot")
        ids = [snapshot.evidence_id for snapshot in self.snapshots]
        if len(ids) != len(set(ids)):
            raise ValueError("validation evidence IDs must be unique")
        if self.multiplicity_family_id is not None and not self.multiplicity_family_id.strip():
            raise ValueError("multiplicity_family_id must be non-empty when supplied")
        if any(not note.strip() for note in self.notes):
            raise ValueError("validation report notes must be non-empty")

    def snapshots_for(self, role: EvidenceRole) -> tuple[EvidenceSnapshot, ...]:
        """Return snapshots for one explicitly requested validation role."""

        return tuple(snapshot for snapshot in self.snapshots if snapshot.role is role)
