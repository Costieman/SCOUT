"""Presentation-only interpretation helpers for Strategy Builder results.

The analytical core remains authoritative for every statistic. This module only turns already-computed
exit-comparison fields into calibrated, plain-English display text and transparent traffic-light cues.
The cues are deliberately descriptive: they are not validation gates, significance tests, forecasts, or
production-promotion decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.risk.exit_policies import ExitFamily
from trade_scout.statistics.exit_research import ExitPolicySummary, ExitResearchComparison


class ReadoutTone(StrEnum):
    """Accessible display tone used alongside text labels; color is never the only signal."""

    POSITIVE = "positive"
    CAUTION = "caution"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ReadoutSignal:
    """One compact explanatory signal derived from already-computed descriptive statistics."""

    label: str
    tone: ReadoutTone
    headline: str
    detail: str


@dataclass(frozen=True, slots=True)
class StrategyPlainEnglishReadout:
    """Plain-English summary of one Strategy Builder comparison."""

    historical_payoff: ReadoutSignal
    exit_tradeoff: ReadoutSignal
    evidence_status: ReadoutSignal
    summary: str
    next_question: str
    definition_version: str = "strategy-builder-plain-english-v0.1"


def build_strategy_plain_english_readout(
    comparison: ExitResearchComparison,
    *,
    research_state: str,
) -> StrategyPlainEnglishReadout:
    """Build a transparent display aid without changing or extending the statistical evidence."""

    hold = _hold_summary(comparison)
    alternatives = tuple(
        item for item in comparison.policy_summaries if item.family is not ExitFamily.HOLD_TO_HORIZON
    )
    historical_payoff = _historical_payoff_signal(hold)
    exit_tradeoff = _exit_tradeoff_signal(hold, alternatives)
    evidence_status = _evidence_signal(research_state)
    summary = _summary_text(comparison, hold, alternatives)
    next_question = _next_question(hold, alternatives)
    return StrategyPlainEnglishReadout(
        historical_payoff=historical_payoff,
        exit_tradeoff=exit_tradeoff,
        evidence_status=evidence_status,
        summary=summary,
        next_question=next_question,
    )


def _hold_summary(comparison: ExitResearchComparison) -> ExitPolicySummary:
    hold = next(
        (item for item in comparison.policy_summaries if item.family is ExitFamily.HOLD_TO_HORIZON),
        None,
    )
    if hold is None:
        raise ValueError("plain-English Strategy Builder readout requires hold-to-horizon baseline")
    return hold


def _historical_payoff_signal(hold: ExitPolicySummary) -> ReadoutSignal:
    expectancy = hold.expectancy
    profit_factor = hold.profit_factor
    if expectancy is None:
        return ReadoutSignal(
            label="Historical payoff",
            tone=ReadoutTone.NEUTRAL,
            headline="Not enough complete outcomes",
            detail="SCOUT cannot summarize average historical payoff from the available completed paths.",
        )
    if expectancy > 0 and (profit_factor is None or profit_factor > 1):
        return ReadoutSignal(
            label="Historical payoff",
            tone=ReadoutTone.POSITIVE,
            headline="Positive in this historical sample",
            detail=(
                f"Average modeled trade return was {expectancy * 100:+.2f}% over the configured maximum "
                "holding period. This is not an annualized portfolio return or a forecast."
            ),
        )
    if expectancy < 0 and (profit_factor is None or profit_factor < 1):
        return ReadoutSignal(
            label="Historical payoff",
            tone=ReadoutTone.NEGATIVE,
            headline="Negative in this historical sample",
            detail=(
                f"Average modeled trade return was {expectancy * 100:+.2f}% over the configured maximum "
                "holding period."
            ),
        )
    return ReadoutSignal(
        label="Historical payoff",
        tone=ReadoutTone.CAUTION,
        headline="Mixed historical payoff",
        detail="The average return and payoff statistics do not point in one clean direction.",
    )


def _exit_tradeoff_signal(
    hold: ExitPolicySummary,
    alternatives: tuple[ExitPolicySummary, ...],
) -> ReadoutSignal:
    if not alternatives:
        return ReadoutSignal(
            label="Exit vs hold",
            tone=ReadoutTone.NEUTRAL,
            headline="No alternative exit compared",
            detail="Hold-to-maximum-period is the only exit policy in this run.",
        )
    ranked = tuple(item for item in alternatives if item.expectancy_delta_vs_hold is not None)
    if not ranked:
        return ReadoutSignal(
            label="Exit vs hold",
            tone=ReadoutTone.NEUTRAL,
            headline="Relative exit effect unavailable",
            detail="SCOUT could not calculate an expectancy difference versus the hold baseline.",
        )
    best = max(ranked, key=lambda item: float(item.expectancy_delta_vs_hold or 0.0))
    best_delta = float(best.expectancy_delta_vs_hold or 0.0)
    threshold = 0.0025
    if best_delta > threshold:
        tone = ReadoutTone.POSITIVE
        headline = "At least one tested exit improved average return"
    elif all(float(item.expectancy_delta_vs_hold or 0.0) < -threshold for item in ranked):
        tone = ReadoutTone.NEGATIVE
        headline = "Every tested exit reduced average return"
    else:
        tone = ReadoutTone.CAUTION
        headline = "Exit effect is small or mixed"
    detail = (
        f"Highest tested expectancy difference versus hold was {best_delta * 100:+.2f} percentage points. "
        "The ±0.25-point traffic-light boundary is only a display aid, not statistical significance."
    )
    if hold.tail_loss_p05 is not None and best.tail_loss_p05 is not None:
        tail_change = best.tail_loss_p05 - hold.tail_loss_p05
        if abs(tail_change) >= 0.0005:
            detail += f" Its 5th-percentile outcome changed by {tail_change * 100:+.2f} points versus hold."
    return ReadoutSignal(label="Exit vs hold", tone=tone, headline=headline, detail=detail)


def _evidence_signal(research_state: str) -> ReadoutSignal:
    normalized = research_state.strip().upper()
    if normalized in {"VALIDATED", "PRODUCTION-ELIGIBLE"}:
        return ReadoutSignal(
            label="Evidence status",
            tone=ReadoutTone.POSITIVE,
            headline=normalized.replace("-", " ").title(),
            detail="The displayed research state reports that the relevant validation gate has been passed.",
        )
    if normalized in {"REJECTED", "NO_EDGE"}:
        return ReadoutSignal(
            label="Evidence status",
            tone=ReadoutTone.NEGATIVE,
            headline="Evidence rejected",
            detail="The registered research state does not support promotion of this definition.",
        )
    if normalized == "EXPLORATORY":
        return ReadoutSignal(
            label="Evidence status",
            tone=ReadoutTone.CAUTION,
            headline="Exploratory — not validated",
            detail=(
                "These results describe the tested historical sample. They do not yet establish long-term or "
                "out-of-sample profitability."
            ),
        )
    return ReadoutSignal(
        label="Evidence status",
        tone=ReadoutTone.NEUTRAL,
        headline=research_state or "Unknown",
        detail="Use the registered research lifecycle state rather than inferring confidence from returns alone.",
    )


def _summary_text(
    comparison: ExitResearchComparison,
    hold: ExitPolicySummary,
    alternatives: tuple[ExitPolicySummary, ...],
) -> str:
    sample = comparison.complete_event_count
    hold_return = "unavailable" if hold.expectancy is None else f"{hold.expectancy * 100:+.2f}%"
    text = (
        f"Across {sample:,} complete historical events, holding to the configured maximum period averaged "
        f"{hold_return} per modeled trade after the configured execution costs."
    )
    if alternatives:
        available = tuple(item for item in alternatives if item.expectancy is not None)
        if available:
            best = max(available, key=lambda item: float(item.expectancy or 0.0))
            delta = best.expectancy_delta_vs_hold
            delta_text = "unknown" if delta is None else f"{delta * 100:+.2f} points"
            text += (
                f" The highest-expectancy alternative exit returned {float(best.expectancy or 0.0) * 100:+.2f}% "
                f"on average, {delta_text} versus hold."
            )
    return text + " Overlapping trades, capital constraints and portfolio compounding are not represented by this number."


def _next_question(
    hold: ExitPolicySummary,
    alternatives: tuple[ExitPolicySummary, ...],
) -> str:
    if not alternatives:
        return "Add one exit family or a one-variable parameter sweep to learn whether trade management changes the outcome distribution."
    best = max(
        alternatives,
        key=lambda item: float(item.expectancy_delta_vs_hold or float("-inf")),
    )
    if best.expectancy_delta_vs_hold is not None and best.expectancy_delta_vs_hold > 0:
        return "Test nearby values of the same exit parameter. A broad plateau is more credible than one isolated best value."
    if hold.tail_loss_p05 is not None and any(
        item.tail_loss_p05 is not None and item.tail_loss_p05 > hold.tail_loss_p05
        for item in alternatives
    ):
        return "The exits appear to trade some return for downside control. Sweep one exit parameter to map that risk/return trade-off rather than selecting one value by eye."
    return "Keep the entry definition fixed and vary one parameter at a time; look for a stable region rather than a single historical optimum."


__all__ = [
    "ReadoutSignal",
    "ReadoutTone",
    "StrategyPlainEnglishReadout",
    "build_strategy_plain_english_readout",
]
