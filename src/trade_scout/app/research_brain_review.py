"""Deterministic descriptive review of a research brain's preserved experiment evidence.

This module summarizes what the brain has actually recorded. It does not estimate statistical
significance, validate a strategy, choose an optimum, or infer production eligibility. Its purpose
is to make the accumulated local evidence easier to understand before any future conditioning or
assistant-driven follow-up layer is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from trade_scout.app.experiment_library_service import ExperimentLibraryDetail
from trade_scout.experiments.contracts import JSONValue
from trade_scout.experiments.research_brains import ResearchBrainSnapshot

if TYPE_CHECKING:
    from trade_scout.app.research_brain_service import ResearchBrainExperimentView


@dataclass(frozen=True, slots=True)
class BrainSweepObservation:
    """One descriptive observation from a saved parameter sweep."""

    experiment_id: str
    variable_label: str
    tested_values: int
    best_observed_value: float | None
    best_observed_expectancy: float | None
    best_observed_complete_events: int | None
    worst_observed_value: float | None
    worst_observed_expectancy: float | None
    smallest_complete_events: int | None
    largest_complete_events: int | None


@dataclass(frozen=True, slots=True)
class ResearchBrainReview:
    """Plain-language evidence inventory for one brain, without scientific promotion."""

    experiment_count: int
    succeeded_count: int
    failed_count: int
    sweep_count: int
    ordinary_run_count: int
    drift_warning_count: int
    unreadable_evidence_count: int
    sweep_observations: tuple[BrainSweepObservation, ...]
    findings: tuple[str, ...]
    cautions: tuple[str, ...]
    next_questions: tuple[str, ...]
    readiness_label: str
    readiness_explanation: str


def build_research_brain_review(
    snapshot: ResearchBrainSnapshot,
    experiments: tuple[ResearchBrainExperimentView, ...],
) -> ResearchBrainReview:
    """Summarize preserved local evidence using transparent deterministic rules only."""

    sweep_observations: list[BrainSweepObservation] = []
    ordinary_runs = 0
    unreadable = 0
    for item in experiments:
        if item.integrity_error is not None or item.experiment is None:
            unreadable += 1
            continue
        observation = _sweep_observation(item.experiment)
        if observation is None:
            ordinary_runs += 1
        else:
            sweep_observations.append(observation)

    resolved_sweeps = tuple(sweep_observations)
    findings = _findings(snapshot, resolved_sweeps, ordinary_runs)
    cautions = _cautions(snapshot, resolved_sweeps, unreadable)
    next_questions = _next_questions(snapshot, resolved_sweeps, unreadable)
    readiness_label, readiness_explanation = _readiness(
        snapshot,
        resolved_sweeps,
        unreadable,
    )
    return ResearchBrainReview(
        experiment_count=len(snapshot.memberships),
        succeeded_count=snapshot.succeeded_count,
        failed_count=snapshot.failed_count,
        sweep_count=len(resolved_sweeps),
        ordinary_run_count=ordinary_runs,
        drift_warning_count=snapshot.drift_warning_count,
        unreadable_evidence_count=unreadable,
        sweep_observations=resolved_sweeps,
        findings=findings,
        cautions=cautions,
        next_questions=next_questions,
        readiness_label=readiness_label,
        readiness_explanation=readiness_explanation,
    )


def _sweep_observation(detail: ExperimentLibraryDetail) -> BrainSweepObservation | None:
    payload = dict(detail.stage_outputs).get("strategy_builder_entry_sweep")
    if payload is None:
        return None
    points = payload.get("points")
    if not isinstance(points, list):
        return BrainSweepObservation(
            experiment_id=detail.manifest.experiment_id,
            variable_label=_variable_label(detail),
            tested_values=0,
            best_observed_value=None,
            best_observed_expectancy=None,
            best_observed_complete_events=None,
            worst_observed_value=None,
            worst_observed_expectancy=None,
            smallest_complete_events=None,
            largest_complete_events=None,
        )

    resolved: list[tuple[float, float, int | None]] = []
    complete_counts: list[int] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        value = _number(
            point.get("parameter_value")
            if "parameter_value" in point
            else point.get("value")
        )
        expectancy = _number(point.get("expectancy_return"))
        complete = _integer(point.get("complete_event_count"))
        if complete is not None:
            complete_counts.append(complete)
        if value is None or expectancy is None:
            continue
        resolved.append((value, expectancy, complete))

    best = max(resolved, key=lambda item: item[1]) if resolved else None
    worst = min(resolved, key=lambda item: item[1]) if resolved else None
    return BrainSweepObservation(
        experiment_id=detail.manifest.experiment_id,
        variable_label=_variable_label(detail),
        tested_values=len(points),
        best_observed_value=best[0] if best is not None else None,
        best_observed_expectancy=best[1] if best is not None else None,
        best_observed_complete_events=best[2] if best is not None else None,
        worst_observed_value=worst[0] if worst is not None else None,
        worst_observed_expectancy=worst[1] if worst is not None else None,
        smallest_complete_events=min(complete_counts) if complete_counts else None,
        largest_complete_events=max(complete_counts) if complete_counts else None,
    )


def _variable_label(detail: ExperimentLibraryDetail) -> str:
    configuration = detail.manifest.definition.resolved_configuration
    variable = configuration.get("research_variable")
    if not isinstance(variable, dict):
        return "saved parameter sweep"
    label = variable.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    feature = variable.get("target_feature_name")
    parameter = variable.get("parameter")
    parts = [str(item) for item in (feature, parameter) if isinstance(item, str) and item.strip()]
    return " · ".join(parts) if parts else "saved parameter sweep"


def _findings(
    snapshot: ResearchBrainSnapshot,
    sweeps: tuple[BrainSweepObservation, ...],
    ordinary_runs: int,
) -> tuple[str, ...]:
    findings: list[str] = []
    if snapshot.memberships:
        findings.append(
            f"This brain currently remembers {len(snapshot.memberships)} experiment(s): "
            f"{snapshot.succeeded_count} succeeded and {snapshot.failed_count} failed."
        )
    if sweeps:
        findings.append(
            f"{len(sweeps)} saved parameter sweep(s) map complete tested ranges rather than only "
            "the historically best cell."
        )
    if ordinary_runs:
        findings.append(
            f"{ordinary_runs} saved run(s) are single configurations rather than parameter sweeps."
        )
    for sweep in sweeps[:4]:
        if sweep.best_observed_value is None or sweep.best_observed_expectancy is None:
            continue
        sample = (
            "unknown complete-event count"
            if sweep.best_observed_complete_events is None
            else f"N={sweep.best_observed_complete_events} complete events"
        )
        findings.append(
            f"In {sweep.variable_label}, the highest historical cell was "
            f"{_format_number(sweep.best_observed_value)} with raw hold expectancy "
            f"{_percent(sweep.best_observed_expectancy)} ({sample}). This is an observed cell, "
            "not a validated optimum."
        )
    return tuple(findings)


def _cautions(
    snapshot: ResearchBrainSnapshot,
    sweeps: tuple[BrainSweepObservation, ...],
    unreadable: int,
) -> tuple[str, ...]:
    cautions: list[str] = []
    if unreadable:
        cautions.append(
            f"{unreadable} attached experiment(s) could not be checksum-verified/read and are not "
            "used in this review."
        )
    if snapshot.failed_count:
        cautions.append(
            f"{snapshot.failed_count} failed experiment(s) are intentionally retained as negative "
            "research history."
        )
    if snapshot.drift_warning_count:
        cautions.append(
            f"{snapshot.drift_warning_count} experiment(s) sit outside a declared brain focus "
            "boundary; they remain visible but should not be silently pooled with in-focus work."
        )
    for sweep in sweeps:
        low = sweep.smallest_complete_events
        high = sweep.largest_complete_events
        if low is not None and high is not None and low < high:
            cautions.append(
                f"{sweep.variable_label} has uneven sample support across cells "
                f"(complete-event N ranges from {low} to {high}). Large raw returns in sparse cells "
                "should be treated as unstable until challenged."
            )
    if not snapshot.memberships:
        cautions.append("There is no experiment evidence in this brain yet.")
    cautions.append(
        "This review does not apply uncertainty intervals, matched comparators, multiplicity "
        "correction, walk-forward testing, or out-of-sample validation unless those already exist "
        "inside a referenced experiment artifact."
    )
    return tuple(cautions)


def _next_questions(
    snapshot: ResearchBrainSnapshot,
    sweeps: tuple[BrainSweepObservation, ...],
    unreadable: int,
) -> tuple[str, ...]:
    questions: list[str] = []
    if unreadable:
        questions.append(
            "Repair or inspect the unreadable experiment evidence before conditioning further."
        )
    if sweeps:
        questions.append(
            "Inspect whether the apparently stronger cells form a broad neighboring region rather "
            "than an isolated maximum."
        )
        questions.append(
            "Repeat the most interesting region with stronger sample support and an appropriate "
            "comparator before treating it as a candidate relationship."
        )
    if snapshot.drift_warning_count:
        questions.append(
            "Decide whether the scope-warning experiments are deliberate boundary tests or belong "
            "in a separate research brain."
        )
    if not sweeps and snapshot.succeeded_count:
        questions.append(
            "Add a controlled one-variable comparison if the research question depends on a "
            "tunable parameter."
        )
    if not snapshot.memberships:
        questions.append("Attach the first relevant experiment to establish the brain's evidence history.")
    return tuple(questions)


def _readiness(
    snapshot: ResearchBrainSnapshot,
    sweeps: tuple[BrainSweepObservation, ...],
    unreadable: int,
) -> tuple[str, str]:
    if not snapshot.memberships:
        return (
            "EMPTY",
            "There is no evidence to review yet. Readiness is based on evidence coverage, not a "
            "fixed run count.",
        )
    if unreadable:
        return (
            "EVIDENCE_CHECK_NEEDED",
            "At least one attached experiment cannot currently be verified, so deeper conditioning "
            "should wait.",
        )
    if snapshot.succeeded_count == 0:
        return (
            "FAILURE_HISTORY_ONLY",
            "The brain contains useful failure history but no successful completed experiment to "
            "compare yet.",
        )
    if sweeps:
        return (
            "DESCRIPTIVE_REVIEW_AVAILABLE",
            "There is enough structured history for a descriptive brain review. This does not mean "
            "there is enough evidence to validate or optimize a strategy.",
        )
    return (
        "BASIC_REVIEW_AVAILABLE",
        "The brain can summarize its saved runs, but it has not yet accumulated a parameter surface "
        "or other structured comparison. Readiness is not inferred from an arbitrary experiment count.",
    )


def _number(value: JSONValue | None) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _integer(value: JSONValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _percent(value: float) -> str:
    return f"{value * 100:+.2f}%"


def _format_number(value: float) -> str:
    return f"{value:g}"


__all__ = [
    "BrainSweepObservation",
    "ResearchBrainReview",
    "build_research_brain_review",
]
