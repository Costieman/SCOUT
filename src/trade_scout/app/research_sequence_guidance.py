"""Plain-English research-order guidance for Strategy Builder experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from trade_scout.experiments.contracts import ExperimentStatus, JSONValue
from trade_scout.statistics.exit_research import ExitResearchComparison

if TYPE_CHECKING:
    from trade_scout.app.research_brain_service import ResearchBrainView


@dataclass(frozen=True, slots=True)
class ResearchSequenceGuidance:
    stage: str
    headline: str
    rationale: str
    next_dimension: str
    evidence_source: str = "current_run"


@dataclass(frozen=True, slots=True)
class ResearchSequenceEvidence:
    """Historical research dimensions already represented in one Research Brain."""

    experiment_count: int = 0
    entry_efficacy: bool = False
    entry_robustness: bool = False
    holding_horizon: bool = False
    exits_risk: bool = False
    execution_sensitivity: bool = False


def guide_research_sequence(
    comparison: ExitResearchComparison,
    *,
    has_entry_sweep: bool = False,
) -> ResearchSequenceGuidance:
    """Recommend the highest-information research stage from the current run only."""

    del comparison
    evidence = ResearchSequenceEvidence(
        experiment_count=1,
        entry_efficacy=has_entry_sweep,
        entry_robustness=has_entry_sweep,
    )
    return guide_research_sequence_from_evidence(evidence, evidence_source="current_run")


def guide_research_sequence_from_brain(view: ResearchBrainView) -> ResearchSequenceGuidance:
    """Recommend the next stage using all checksum-verified experiments in a Research Brain."""

    evidence = summarize_brain_sequence_evidence(view)
    return guide_research_sequence_from_evidence(evidence, evidence_source="research_brain")


def guide_research_sequence_from_evidence(
    evidence: ResearchSequenceEvidence,
    *,
    evidence_source: str = "research_brain",
) -> ResearchSequenceGuidance:
    """Choose the first research dimension not yet represented by preserved evidence."""

    if not evidence.entry_efficacy:
        return ResearchSequenceGuidance(
            stage="ENTRY_EFFICACY",
            headline="Establish the entry before optimizing trade management.",
            rationale=(
                "The preserved research history does not yet establish a completed entry-efficacy "
                "experiment. Optimizing later dimensions first can polish noise rather than improve "
                "a reproducible signal."
            ),
            next_dimension="Test the entry against the hold outcome before changing exits or costs.",
            evidence_source=evidence_source,
        )
    if not evidence.entry_robustness:
        return ResearchSequenceGuidance(
            stage="ENTRY_ROBUSTNESS",
            headline="The entry has evidence; test its parameter neighborhood next.",
            rationale=(
                "A completed entry result exists, but the Brain does not yet contain a sufficiently "
                "resolved entry sweep. One historical cell is not enough to establish robustness."
            ),
            next_dimension="Sweep the entry parameter across neighboring values and preserve the run.",
            evidence_source=evidence_source,
        )
    if not evidence.holding_horizon:
        return ResearchSequenceGuidance(
            stage="HOLDING_HORIZON",
            headline="Entry robustness exists; test holding-horizon sensitivity next.",
            rationale=(
                "The Brain contains entry and neighborhood evidence, but not multiple completed "
                "holding horizons. Exit conclusions remain hard to interpret until time-in-trade "
                "sensitivity is separated from stop and target effects."
            ),
            next_dimension="Compare at least two materially different holding horizons.",
            evidence_source=evidence_source,
        )
    if not evidence.exits_risk:
        return ResearchSequenceGuidance(
            stage="EXITS_RISK",
            headline="The signal and horizon are characterized; research exits and risk next.",
            rationale=(
                "Earlier research dimensions are represented in the Brain. Stops, targets and risk "
                "controls can now be interpreted against a better-defined entry and holding policy."
            ),
            next_dimension="Test one exit or risk variable at a time against the hold control.",
            evidence_source=evidence_source,
        )
    if not evidence.execution_sensitivity:
        return ResearchSequenceGuidance(
            stage="EXECUTION_SENSITIVITY",
            headline="Core strategy research exists; stress execution assumptions next.",
            rationale=(
                "The Brain contains entry, horizon and exit/risk evidence, but no preserved cost or "
                "execution-sensitivity experiment. Apparent edge should be stressed before validation."
            ),
            next_dimension="Vary costs, slippage or another explicit execution assumption.",
            evidence_source=evidence_source,
        )
    return ResearchSequenceGuidance(
        stage="VALIDATION",
        headline="The main research sequence is represented; move toward validation.",
        rationale=(
            "The Brain contains evidence for entry efficacy, entry robustness, holding horizon, "
            "exit/risk behavior and execution sensitivity. More in-sample honing now has lower "
            "information value than governed validation."
        ),
        next_dimension="Freeze the hypothesis and run the governed validation workflow.",
        evidence_source=evidence_source,
    )


def summarize_brain_sequence_evidence(view: ResearchBrainView) -> ResearchSequenceEvidence:
    """Infer completed research dimensions conservatively from preserved Brain experiments."""

    successful = tuple(
        item.experiment
        for item in view.experiments
        if item.experiment is not None
        and item.experiment.manifest.status is ExperimentStatus.SUCCEEDED
    )
    entry_efficacy = bool(successful)
    entry_robustness = any(
        detail.result is not None
        and detail.result.kind == "strategy_builder_entry_sweep"
        and (detail.result.sweep_point_count or 0) >= 3
        for detail in successful
    )
    horizons = {
        value
        for detail in successful
        for value in _named_numeric_values(
            detail.manifest.definition.resolved_configuration,
            tokens=("horizon", "holding_period", "holding_sessions"),
        )
    }
    exits_risk = any(
        _contains_named_configuration(
            detail.manifest.definition.resolved_configuration,
            tokens=("stop", "target", "exit", "risk"),
        )
        for detail in successful
    )
    execution = any(
        _contains_named_configuration(
            detail.manifest.definition.resolved_configuration,
            tokens=("slippage", "commission", "transaction_cost", "execution_cost", "spread"),
        )
        for detail in successful
    )
    return ResearchSequenceEvidence(
        experiment_count=len(successful),
        entry_efficacy=entry_efficacy,
        entry_robustness=entry_robustness,
        holding_horizon=len(horizons) >= 2,
        exits_risk=exits_risk,
        execution_sensitivity=execution,
    )


def _contains_named_configuration(value: JSONValue, *, tokens: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.casefold()
            if any(token in normalized for token in tokens) and _meaningful(child):
                return True
            if _contains_named_configuration(child, tokens=tokens):
                return True
    elif isinstance(value, list):
        return any(_contains_named_configuration(item, tokens=tokens) for item in value)
    return False


def _named_numeric_values(value: JSONValue, *, tokens: tuple[str, ...]) -> tuple[float, ...]:
    found: list[float] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.casefold()
            if any(token in normalized for token in tokens):
                if isinstance(child, int | float) and not isinstance(child, bool):
                    found.append(float(child))
            found.extend(_named_numeric_values(child, tokens=tokens))
    elif isinstance(value, list):
        for item in value:
            found.extend(_named_numeric_values(item, tokens=tokens))
    return tuple(found)


def _meaningful(value: JSONValue) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "none", "disabled", "off", "hold_to_horizon"}
    if isinstance(value, list | dict):
        return bool(value)
    return True


__all__ = [
    "ResearchSequenceEvidence",
    "ResearchSequenceGuidance",
    "guide_research_sequence",
    "guide_research_sequence_from_brain",
    "guide_research_sequence_from_evidence",
    "summarize_brain_sequence_evidence",
]
