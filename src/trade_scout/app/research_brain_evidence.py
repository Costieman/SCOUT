"""Read-only governed-evidence coverage for research-brain experiment history.

This module summarizes which checksum-verified validation artifacts exist. It does not recompute
statistics, score evidence quality, select a winner, or infer a research-decision state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from trade_scout.validation.evidence import ComparatorKind, EvidenceRole
from trade_scout.validation.reporting import ValidationReviewBundle
from trade_scout.validation.store import FileValidationReviewStore, ValidationReviewStoreError


class BrainEvidenceCoverageState(StrEnum):
    """Highest observed governed evidence role, not a scientific pass/fail state."""

    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"
    VALIDATION_REVIEW_PRESENT = "VALIDATION_REVIEW_PRESENT"
    TIME_ORDERED_EVIDENCE_PRESENT = "TIME_ORDERED_EVIDENCE_PRESENT"
    FINAL_HOLDOUT_PRESENT = "FINAL_HOLDOUT_PRESENT"


@dataclass(frozen=True, slots=True)
class BrainExperimentEvidenceCoverage:
    """Governed validation evidence linked to one immutable experiment."""

    experiment_id: str
    coverage_state: BrainEvidenceCoverageState
    report_ids: tuple[str, ...]
    roles: tuple[EvidenceRole, ...]
    comparator_kinds: tuple[ComparatorKind, ...]
    has_uncertainty_intervals: bool
    has_parameter_surfaces: bool
    has_multiplicity_metadata: bool
    has_robustness_evidence: bool
    review_warning_count: int

    @property
    def has_governed_review(self) -> bool:
        """Return whether at least one checksum-verified validation review was found."""

        return bool(self.report_ids)


@dataclass(frozen=True, slots=True)
class ResearchBrainEvidenceSummary:
    """Coverage inventory for a complete brain without collapsing it into one score."""

    experiments: tuple[BrainExperimentEvidenceCoverage, ...]
    reviewed_experiment_count: int
    validation_experiment_count: int
    walk_forward_experiment_count: int
    final_holdout_experiment_count: int
    robustness_experiment_count: int
    comparator_experiment_count: int
    uncertainty_experiment_count: int
    multiplicity_experiment_count: int
    store_integrity_errors: tuple[str, ...]
    next_challenge: str
    interpretation_boundary: str = (
        "Evidence coverage describes what has been challenged and persisted. It does not say that "
        "the strategy passed, is robust, is validated, or should be traded."
    )


@dataclass(slots=True)
class _CoverageAccumulator:
    report_ids: list[str]
    roles: set[EvidenceRole]
    comparator_kinds: set[ComparatorKind]
    has_uncertainty_intervals: bool = False
    has_parameter_surfaces: bool = False
    has_multiplicity_metadata: bool = False
    has_robustness_evidence: bool = False
    review_warning_count: int = 0


def _accumulator() -> _CoverageAccumulator:
    return _CoverageAccumulator(report_ids=[], roles=set(), comparator_kinds=set())


class ResearchBrainEvidenceService:
    """Read the canonical validation-review store and describe evidence coverage only."""

    def __init__(self, validation_review_root: Path) -> None:
        self._root = validation_review_root
        self._store = FileValidationReviewStore(validation_review_root)

    @property
    def validation_review_root(self) -> Path:
        """Return the configured governed validation-review root."""

        return self._root

    def experiment_coverage(self, experiment_id: str) -> BrainExperimentEvidenceCoverage:
        """Summarize verified validation reviews linked to one experiment."""

        summary = self.brain_summary((experiment_id,))
        return summary.experiments[0]

    def brain_summary(self, experiment_ids: tuple[str, ...]) -> ResearchBrainEvidenceSummary:
        """Summarize evidence coverage across attached experiments without a composite score."""

        if any(not item.strip() for item in experiment_ids):
            raise ValueError("brain evidence summary experiment IDs must be non-empty")
        if len(experiment_ids) != len(set(experiment_ids)):
            raise ValueError("brain evidence summary requires unique experiment IDs")

        accumulators = {experiment_id: _accumulator() for experiment_id in experiment_ids}
        store_errors: list[str] = []
        for report_id in self._store.list_report_ids():
            try:
                bundle = self._store.read(report_id)
            except (OSError, ValueError, ValidationReviewStoreError) as exc:
                store_errors.append(f"{report_id}: {type(exc).__name__}: {exc}")
                continue
            accumulator = accumulators.get(bundle.report.experiment_id)
            if accumulator is None:
                continue
            _add_bundle(accumulator, bundle)

        experiments = tuple(
            _coverage(experiment_id, accumulators[experiment_id]) for experiment_id in experiment_ids
        )
        return ResearchBrainEvidenceSummary(
            experiments=experiments,
            reviewed_experiment_count=sum(item.has_governed_review for item in experiments),
            validation_experiment_count=sum(
                EvidenceRole.VALIDATION in item.roles for item in experiments
            ),
            walk_forward_experiment_count=sum(
                EvidenceRole.WALK_FORWARD in item.roles for item in experiments
            ),
            final_holdout_experiment_count=sum(
                EvidenceRole.FINAL_HOLDOUT in item.roles for item in experiments
            ),
            robustness_experiment_count=sum(item.has_robustness_evidence for item in experiments),
            comparator_experiment_count=sum(bool(item.comparator_kinds) for item in experiments),
            uncertainty_experiment_count=sum(
                item.has_uncertainty_intervals for item in experiments
            ),
            multiplicity_experiment_count=sum(
                item.has_multiplicity_metadata for item in experiments
            ),
            store_integrity_errors=tuple(store_errors),
            next_challenge=_next_challenge(experiments),
        )


def _add_bundle(accumulator: _CoverageAccumulator, bundle: ValidationReviewBundle) -> None:
    accumulator.report_ids.append(bundle.report.report_id)
    accumulator.has_parameter_surfaces = (
        accumulator.has_parameter_surfaces or bool(bundle.parameter_surfaces)
    )
    accumulator.has_multiplicity_metadata = (
        accumulator.has_multiplicity_metadata or bool(bundle.multiplicity)
    )
    accumulator.has_robustness_evidence = (
        accumulator.has_robustness_evidence or bundle.robustness_plan_id is not None
    )
    for snapshot in bundle.report.snapshots:
        accumulator.roles.add(snapshot.role)
        accumulator.review_warning_count += len(snapshot.warnings)
        if snapshot.role is EvidenceRole.ROBUSTNESS:
            accumulator.has_robustness_evidence = True
        for metric in snapshot.metrics:
            accumulator.has_uncertainty_intervals = (
                accumulator.has_uncertainty_intervals or metric.interval is not None
            )
        for effect in snapshot.effects:
            accumulator.comparator_kinds.add(effect.comparator.kind)
            accumulator.has_uncertainty_intervals = (
                accumulator.has_uncertainty_intervals or effect.interval is not None
            )


def _coverage(
    experiment_id: str,
    accumulator: _CoverageAccumulator,
) -> BrainExperimentEvidenceCoverage:
    roles = tuple(role for role in EvidenceRole if role in accumulator.roles)
    comparators = tuple(
        kind for kind in ComparatorKind if kind in accumulator.comparator_kinds
    )
    return BrainExperimentEvidenceCoverage(
        experiment_id=experiment_id,
        coverage_state=_coverage_state(accumulator.roles, bool(accumulator.report_ids)),
        report_ids=tuple(sorted(accumulator.report_ids)),
        roles=roles,
        comparator_kinds=comparators,
        has_uncertainty_intervals=accumulator.has_uncertainty_intervals,
        has_parameter_surfaces=accumulator.has_parameter_surfaces,
        has_multiplicity_metadata=accumulator.has_multiplicity_metadata,
        has_robustness_evidence=accumulator.has_robustness_evidence,
        review_warning_count=accumulator.review_warning_count,
    )


def _coverage_state(
    roles: set[EvidenceRole],
    has_review: bool,
) -> BrainEvidenceCoverageState:
    if EvidenceRole.FINAL_HOLDOUT in roles:
        return BrainEvidenceCoverageState.FINAL_HOLDOUT_PRESENT
    if EvidenceRole.WALK_FORWARD in roles:
        return BrainEvidenceCoverageState.TIME_ORDERED_EVIDENCE_PRESENT
    if has_review:
        return BrainEvidenceCoverageState.VALIDATION_REVIEW_PRESENT
    return BrainEvidenceCoverageState.EXPLORATORY_ONLY


def _next_challenge(experiments: tuple[BrainExperimentEvidenceCoverage, ...]) -> str:
    if not experiments:
        return "Add saved experiments before asking this brain for a research-direction summary."
    if not any(item.has_governed_review for item in experiments):
        return (
            "The brain currently contains exploratory history only. Freeze a specific candidate "
            "hypothesis and challenge it through the governed validation workflow instead of "
            "continuing to tune the same historical peak."
        )
    if not any(item.comparator_kinds for item in experiments):
        return (
            "No governed review in this brain contains a comparator effect. Predeclare an "
            "appropriate comparator before adding more strategy variables."
        )
    if not any(item.has_uncertainty_intervals for item in experiments):
        return (
            "Comparator evidence exists, but no linked governed review exposes uncertainty "
            "intervals. Add uncertainty before treating effect size as stable."
        )
    if not any(EvidenceRole.WALK_FORWARD in item.roles for item in experiments):
        return (
            "Governed validation evidence exists, but no walk-forward evidence is linked. Freeze "
            "the candidate and test it through time before broadening the search."
        )
    if not any(item.has_robustness_evidence for item in experiments):
        return (
            "Time-ordered evidence exists, but no governed robustness challenge is linked. Test "
            "nearby parameters and predeclared reasonable perturbations before relying on the result."
        )
    if not any(EvidenceRole.FINAL_HOLDOUT in item.roles for item in experiments):
        return (
            "The brain has validation, time-ordered and robustness evidence, but no final holdout "
            "is linked. Keep the holdout untouched until the candidate definition is fully frozen."
        )
    return (
        "This brain contains governed comparator, uncertainty, time-ordered, robustness and final "
        "holdout evidence. Review the explicit research decision and rationale; evidence coverage "
        "alone does not determine whether the hypothesis passed."
    )


__all__ = [
    "BrainEvidenceCoverageState",
    "BrainExperimentEvidenceCoverage",
    "ResearchBrainEvidenceService",
    "ResearchBrainEvidenceSummary",
]
