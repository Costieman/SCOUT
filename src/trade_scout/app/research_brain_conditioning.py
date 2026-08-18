"""Evidence-quality conditioning for one research brain.

Conditioning v1 does not score, rank, validate, or optimize experiments. It inspects the exact
checksum-verified artifacts already attached to a brain and reports which evidence dimensions are
present, partial, missing, or unreadable. The purpose is to tell the researcher what should be
challenged next without turning exploratory history into a strategy recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from trade_scout.app.experiment_library_service import ExperimentLibraryDetail
from trade_scout.experiments.contracts import JSONValue

if TYPE_CHECKING:
    from trade_scout.app.research_brain_service import ResearchBrainView


class ConditioningState(StrEnum):
    """Plain evidence-coverage state for one conditioning dimension."""

    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    CHECK_NEEDED = "CHECK_NEEDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class ConditioningDimension:
    """One independently reported evidence-quality dimension."""

    key: str
    label: str
    state: ConditioningState
    summary: str
    evidence: tuple[str, ...] = ()
    next_step: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchBrainConditioning:
    """Transparent evidence map with one prioritized follow-up and no composite score."""

    dimensions: tuple[ConditioningDimension, ...]
    priority_key: str | None
    priority_title: str
    priority_action: str
    boundary: str = (
        "Conditioning reports evidence coverage only. It does not validate a strategy, select an "
        "optimum, create a production signal, or replace formal statistical review."
    )
    version: str = "research-brain-conditioning-v0.1"

    def dimension(self, key: str) -> ConditioningDimension:
        """Return one named conditioning dimension or fail explicitly."""

        for item in self.dimensions:
            if item.key == key:
                return item
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class _SweepPoint:
    value: float
    expectancy: float
    complete_event_count: int | None


@dataclass(frozen=True, slots=True)
class _SweepEvidence:
    experiment_id: str
    label: str
    points: tuple[_SweepPoint, ...]


_COMPARATOR_TOKENS = (
    "comparator",
    "baseline",
    "benchmark_relative",
    "benchmark_excess",
    "excess_return",
    "excess_vs",
    "paired_difference",
    "control_return",
)
_UNCERTAINTY_TOKENS = (
    "confidence_interval",
    "confidence_bounds",
    "bootstrap_interval",
    "wilson_interval",
    "standard_error",
    "p_value",
    "pvalue",
    "adjusted_p",
    "uncertainty_interval",
)
_OOS_TOKENS = (
    "out_of_sample",
    "outofsample",
    "oos_",
    "holdout_result",
    "holdout_expectancy",
    "unseen_result",
    "validation_result",
)
_TIME_TOKENS = (
    "walk_forward",
    "walkforward",
    "fold_results",
    "validation_folds",
    "year_results",
    "by_year",
    "time_window_results",
    "period_results",
)
_MULTIPLICITY_TOKENS = (
    "multiplicity",
    "benjamini",
    "bonferroni",
    "false_discovery",
    "fdr",
    "adjusted_p",
)
_SAMPLE_KEYS = {
    "complete_event_count",
    "sample_count",
    "effective_sample_count",
    "event_count",
    "unique_event_count",
}


def build_research_brain_conditioning(view: ResearchBrainView) -> ResearchBrainConditioning:
    """Build a deterministic evidence map from the brain's currently verified experiment artifacts."""

    readable = tuple(
        item.experiment
        for item in view.experiments
        if item.integrity_error is None and item.experiment is not None
    )
    unreadable_count = sum(
        item.integrity_error is not None or item.experiment is None for item in view.experiments
    )
    sweeps = tuple(
        sweep for detail in readable for sweep in (_sweep_evidence(detail),) if sweep is not None
    )
    sample_counts = _sample_counts(readable)
    comparator_hits = _artifact_hits(readable, _COMPARATOR_TOKENS)
    uncertainty_hits = _artifact_hits(readable, _UNCERTAINTY_TOKENS)
    oos_hits = _artifact_hits(readable, _OOS_TOKENS)
    time_hits = _artifact_hits(readable, _TIME_TOKENS)
    multiplicity_hits = _artifact_hits(readable, _MULTIPLICITY_TOKENS)

    dimensions = (
        _integrity_dimension(view, unreadable_count),
        _sample_dimension(sample_counts),
        _comparator_dimension(comparator_hits),
        _uncertainty_dimension(uncertainty_hits),
        _parameter_stability_dimension(sweeps),
        _time_stability_dimension(time_hits),
        _oos_dimension(oos_hits),
        _search_burden_dimension(sweeps, multiplicity_hits),
    )
    priority_key, priority_title, priority_action = _priority(dimensions, bool(sweeps))
    return ResearchBrainConditioning(
        dimensions=dimensions,
        priority_key=priority_key,
        priority_title=priority_title,
        priority_action=priority_action,
    )


def _integrity_dimension(
    view: ResearchBrainView,
    unreadable_count: int,
) -> ConditioningDimension:
    total = len(view.experiments)
    if total == 0:
        return ConditioningDimension(
            key="integrity",
            label="Evidence integrity",
            state=ConditioningState.MISSING,
            summary="No experiment evidence has been attached to this brain yet.",
            next_step="Attach a relevant saved experiment before conditioning the research question.",
        )
    if unreadable_count:
        return ConditioningDimension(
            key="integrity",
            label="Evidence integrity",
            state=ConditioningState.CHECK_NEEDED,
            summary=(
                f"{unreadable_count} of {total} attached experiment(s) could not be verified or read. "
                "Those experiments are excluded from the other conditioning dimensions."
            ),
            next_step="Repair or inspect unreadable experiment evidence before deeper conditioning.",
        )
    return ConditioningDimension(
        key="integrity",
        label="Evidence integrity",
        state=ConditioningState.AVAILABLE,
        summary=f"All {total} attached experiment record(s) are checksum-verified and readable.",
        evidence=("Exact experiment-manifest bindings verified by the research-brain store.",),
    )


def _sample_dimension(counts: tuple[int, ...]) -> ConditioningDimension:
    if not counts:
        return ConditioningDimension(
            key="sample_support",
            label="Sample support",
            state=ConditioningState.MISSING,
            summary=(
                "No recognized event/sample counts were found in the readable artifacts. SCOUT will "
                "not invent a minimum-sample judgment from absent metadata."
            ),
            next_step="Persist event/sample counts with the next relevant experiment result.",
        )
    low = min(counts)
    high = max(counts)
    if low != high:
        return ConditioningDimension(
            key="sample_support",
            label="Sample support",
            state=ConditioningState.PARTIAL,
            summary=(
                f"Recorded event support varies from N={low} to N={high} across the attached result "
                "cells/summaries. The system reports that unevenness without imposing an arbitrary "
                "strong/moderate/weak sample threshold."
            ),
            evidence=(f"Observed recognized sample counts: {_compact_counts(counts)}",),
            next_step=(
                "Interpret attractive cells together with their own N and effective-sample evidence; "
                "do not compare raw returns without the support counts beside them."
            ),
        )
    return ConditioningDimension(
        key="sample_support",
        label="Sample support",
        state=ConditioningState.AVAILABLE,
        summary=(
            f"The readable evidence records N={low}. This confirms that sample metadata exists, but "
            "does not by itself establish effective-sample strength or independence."
        ),
        evidence=(f"Recognized sample count: N={low}",),
    )


def _comparator_dimension(hits: tuple[str, ...]) -> ConditioningDimension:
    if not hits:
        return ConditioningDimension(
            key="comparator",
            label="Comparison evidence",
            state=ConditioningState.MISSING,
            summary=(
                "No explicit comparator/baseline result was found in the attached artifacts. Raw "
                "positive returns can therefore still be ordinary market or trend drift."
            ),
            next_step=(
                "Run the same fixed research question against an appropriate baseline/control before "
                "expanding the parameter search."
            ),
        )
    return ConditioningDimension(
        key="comparator",
        label="Comparison evidence",
        state=ConditioningState.AVAILABLE,
        summary="At least one attached artifact contains explicit comparator or baseline evidence.",
        evidence=_limited(hits),
    )


def _uncertainty_dimension(hits: tuple[str, ...]) -> ConditioningDimension:
    if not hits:
        return ConditioningDimension(
            key="uncertainty",
            label="Uncertainty",
            state=ConditioningState.MISSING,
            summary=(
                "No confidence interval, bootstrap interval, standard error, p-value, or adjusted "
                "inference field was found in the attached artifacts."
            ),
            next_step=(
                "Add uncertainty estimation to the fixed comparison before treating differences as "
                "more than descriptive."
            ),
        )
    return ConditioningDimension(
        key="uncertainty",
        label="Uncertainty",
        state=ConditioningState.AVAILABLE,
        summary="The attached evidence includes at least one explicit uncertainty/inference result.",
        evidence=_limited(hits),
    )


def _parameter_stability_dimension(
    sweeps: tuple[_SweepEvidence, ...],
) -> ConditioningDimension:
    if not sweeps:
        return ConditioningDimension(
            key="parameter_stability",
            label="Parameter neighborhood",
            state=ConditioningState.NOT_APPLICABLE,
            summary=(
                "No readable one-variable parameter sweep is attached, so there is no parameter "
                "surface for this brain to inspect yet."
            ),
        )

    mapped = tuple(item for item in sweeps if len(item.points) >= 3)
    if not mapped:
        return ConditioningDimension(
            key="parameter_stability",
            label="Parameter neighborhood",
            state=ConditioningState.PARTIAL,
            summary=(
                "A parameter sweep is present, but fewer than three numeric result points are "
                "available in each readable sweep. Neighbor behavior cannot be described reliably."
            ),
            next_step="Map enough neighboring values to see the local response surface and sample sizes.",
        )

    evidence = tuple(_neighbor_description(item) for item in mapped[:4])
    return ConditioningDimension(
        key="parameter_stability",
        label="Parameter neighborhood",
        state=ConditioningState.AVAILABLE,
        summary=(
            f"{len(mapped)} sweep(s) contain enough ordered cells to show the immediate neighbors "
            "around the highest historical cell. This maps the neighborhood; it does not label the "
            "region statistically stable without comparator and uncertainty evidence."
        ),
        evidence=evidence,
    )


def _time_stability_dimension(hits: tuple[str, ...]) -> ConditioningDimension:
    if not hits:
        return ConditioningDimension(
            key="time_stability",
            label="Time stability",
            state=ConditioningState.MISSING,
            summary=(
                "No walk-forward, fold, year-by-year, or other explicit time-sliced result was found "
                "in the attached artifacts."
            ),
            next_step=(
                "After the candidate question is frozen, compare it across time-ordered periods or "
                "walk-forward folds."
            ),
        )
    return ConditioningDimension(
        key="time_stability",
        label="Time stability",
        state=ConditioningState.AVAILABLE,
        summary="The attached evidence includes at least one explicit time-sliced stability result.",
        evidence=_limited(hits),
    )


def _oos_dimension(hits: tuple[str, ...]) -> ConditioningDimension:
    if not hits:
        return ConditioningDimension(
            key="out_of_sample",
            label="Out-of-sample evidence",
            state=ConditioningState.MISSING,
            summary=(
                "No explicit out-of-sample, holdout, unseen-period, or validation-result field was "
                "found in the attached artifacts."
            ),
            next_step=(
                "Do not call the relationship validated. Freeze a compact candidate only after the "
                "exploratory evidence is sufficiently controlled, then test unseen data."
            ),
        )
    return ConditioningDimension(
        key="out_of_sample",
        label="Out-of-sample evidence",
        state=ConditioningState.AVAILABLE,
        summary="The attached evidence includes at least one explicit unseen/holdout result.",
        evidence=_limited(hits),
    )


def _search_burden_dimension(
    sweeps: tuple[_SweepEvidence, ...],
    multiplicity_hits: tuple[str, ...],
) -> ConditioningDimension:
    cells = sum(len(item.points) for item in sweeps)
    if cells == 0:
        return ConditioningDimension(
            key="search_burden",
            label="Search burden",
            state=ConditioningState.AVAILABLE,
            summary=(
                "No readable parameter-sweep cells are attached to this brain. There is no sweep "
                "search burden to report from the currently readable artifacts."
            ),
        )
    if not multiplicity_hits:
        return ConditioningDimension(
            key="search_burden",
            label="Search burden",
            state=ConditioningState.PARTIAL,
            summary=(
                f"This brain includes {cells} readable tested sweep cell(s) across {len(sweeps)} "
                "sweep(s), but no explicit multiplicity/search-adjustment result was found."
            ),
            evidence=tuple(
                f"{item.label}: {len(item.points)} tested numeric cell(s)" for item in sweeps[:6]
            ),
            next_step=(
                "Keep the full tested family visible and apply the appropriate hypothesis-family "
                "correction before making formal claims from the searched cells."
            ),
        )
    return ConditioningDimension(
        key="search_burden",
        label="Search burden",
        state=ConditioningState.AVAILABLE,
        summary=(
            f"This brain includes {cells} readable tested sweep cell(s) across {len(sweeps)} "
            "sweep(s), and explicit multiplicity/search-adjustment evidence is present."
        ),
        evidence=_limited(multiplicity_hits),
    )


def _priority(
    dimensions: tuple[ConditioningDimension, ...],
    has_sweeps: bool,
) -> tuple[str | None, str, str]:
    by_key = {item.key: item for item in dimensions}
    integrity = by_key["integrity"]
    if integrity.state is ConditioningState.CHECK_NEEDED:
        return (
            "integrity",
            "First repair the evidence record",
            integrity.next_step or "Inspect unreadable experiment evidence.",
        )
    if integrity.state is ConditioningState.MISSING:
        return (
            "integrity",
            "First add evidence",
            integrity.next_step or "Attach a relevant saved experiment.",
        )

    order = ["comparator", "uncertainty"]
    if has_sweeps:
        order.extend(("parameter_stability", "search_burden"))
    order.extend(("out_of_sample", "time_stability"))
    for key in order:
        item = by_key[key]
        if item.state in {ConditioningState.MISSING, ConditioningState.PARTIAL}:
            return (
                key,
                f"Next evidence priority: {item.label}",
                item.next_step or f"Strengthen the {item.label.lower()} evidence before expanding.",
            )
    return (
        None,
        "No obvious coverage gap in these conditioning dimensions",
        (
            "Do not tune further by default. Review whether a compact hypothesis is ready for a "
            "governed frozen validation decision using the formal validation workflow."
        ),
    )


def _sweep_evidence(detail: ExperimentLibraryDetail) -> _SweepEvidence | None:
    payload = dict(detail.stage_outputs).get("strategy_builder_entry_sweep")
    if payload is None:
        return None
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        return _SweepEvidence(
            experiment_id=detail.manifest.experiment_id,
            label=_variable_label(detail),
            points=(),
        )
    points: list[_SweepPoint] = []
    for raw in raw_points:
        if not isinstance(raw, dict):
            continue
        value = _number(
            raw.get("parameter_value") if "parameter_value" in raw else raw.get("value")
        )
        expectancy = _number(raw.get("expectancy_return"))
        count = _integer(raw.get("complete_event_count"))
        if value is None or expectancy is None:
            continue
        points.append(
            _SweepPoint(
                value=value,
                expectancy=expectancy,
                complete_event_count=count,
            )
        )
    return _SweepEvidence(
        experiment_id=detail.manifest.experiment_id,
        label=_variable_label(detail),
        points=tuple(sorted(points, key=lambda item: item.value)),
    )


def _variable_label(detail: ExperimentLibraryDetail) -> str:
    variable = detail.manifest.definition.resolved_configuration.get("research_variable")
    if not isinstance(variable, dict):
        return "saved parameter sweep"
    label = variable.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    feature = variable.get("target_feature_name")
    parameter = variable.get("parameter")
    parts = tuple(
        item.strip() for item in (feature, parameter) if isinstance(item, str) and item.strip()
    )
    return " · ".join(parts) if parts else "saved parameter sweep"


def _neighbor_description(sweep: _SweepEvidence) -> str:
    best_index = max(range(len(sweep.points)), key=lambda index: sweep.points[index].expectancy)
    best = sweep.points[best_index]
    left = sweep.points[best_index - 1] if best_index > 0 else None
    right = sweep.points[best_index + 1] if best_index + 1 < len(sweep.points) else None
    parts = [
        f"{sweep.label}: historical peak {_format_number(best.value)} at {_percent(best.expectancy)}"
    ]
    if left is not None:
        parts.append(f"left neighbor {_format_number(left.value)} at {_percent(left.expectancy)}")
    if right is not None:
        parts.append(
            f"right neighbor {_format_number(right.value)} at {_percent(right.expectancy)}"
        )
    best_n = best.complete_event_count
    if best_n is not None:
        parts.append(f"peak-cell N={best_n}")
    return "; ".join(parts) + "."


def _sample_counts(details: tuple[ExperimentLibraryDetail, ...]) -> tuple[int, ...]:
    counts: list[int] = []
    for detail in details:
        for _, payload in detail.stage_outputs:
            _collect_sample_counts(payload, counts)
    return tuple(counts)


def _collect_sample_counts(value: JSONValue, counts: list[int]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.casefold()
            if normalized in _SAMPLE_KEYS:
                resolved = _integer(item)
                if resolved is not None and resolved >= 0:
                    counts.append(resolved)
            _collect_sample_counts(item, counts)
    elif isinstance(value, list):
        for item in value:
            _collect_sample_counts(item, counts)


def _artifact_hits(
    details: tuple[ExperimentLibraryDetail, ...],
    tokens: tuple[str, ...],
) -> tuple[str, ...]:
    hits: list[str] = []
    for detail in details:
        for stage_name, payload in detail.stage_outputs:
            _collect_key_hits(
                payload,
                tokens,
                prefix=f"{detail.manifest.experiment_id}:{stage_name}",
                hits=hits,
            )
    return tuple(dict.fromkeys(hits))


def _collect_key_hits(
    value: JSONValue,
    tokens: tuple[str, ...],
    *,
    prefix: str,
    hits: list[str],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            normalized = key.casefold()
            if any(token in normalized for token in tokens) and _has_evidence_value(item):
                hits.append(path)
            _collect_key_hits(item, tokens, prefix=path, hits=hits)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_key_hits(item, tokens, prefix=f"{prefix}[{index}]", hits=hits)


def _has_evidence_value(value: JSONValue) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().upper() not in {
            "NOT_RUN",
            "NOT_TESTED",
            "NONE",
        }
    if isinstance(value, list | dict):
        return bool(value)
    return True


def _number(value: JSONValue | None) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _integer(value: JSONValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _limited(items: tuple[str, ...], limit: int = 5) -> tuple[str, ...]:
    return items[:limit]


def _compact_counts(counts: tuple[int, ...]) -> str:
    unique = sorted(set(counts))
    if len(unique) <= 12:
        return ", ".join(str(item) for item in unique)
    return f"{', '.join(str(item) for item in unique[:6])}, …, {', '.join(str(item) for item in unique[-3:])}"


def _percent(value: float) -> str:
    return f"{value * 100:+.2f}%"


def _format_number(value: float) -> str:
    return f"{value:g}"


__all__ = [
    "ConditioningDimension",
    "ConditioningState",
    "ResearchBrainConditioning",
    "build_research_brain_conditioning",
]
