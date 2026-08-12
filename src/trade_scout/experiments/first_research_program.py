"""Executable planning metadata for the first consolidation-breakout research program.

This module turns the accepted A-J program sequence into machine-readable planning contracts. It
contains no detector, outcome, risk, or statistical implementation; it only declares what each
experiment is intended to study and which prior stages must exist before it is run.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FirstProgramExperiment(StrEnum):
    """Stable identifiers for the controlled Experiment A-J sequence."""

    A_TREND_BASELINE = "A"
    B_DURATION = "B"
    C_TIGHTNESS = "C"
    D_BREAKOUT = "D"
    E_VOLUME = "E"
    F_REGIME = "F"
    G_VOLATILITY_AGE = "G"
    H_STOPS = "H"
    I_COMBINED_VALIDATION = "I"
    J_WALK_FORWARD_HOLDOUT = "J"


@dataclass(frozen=True, slots=True)
class ProgramStep:
    """One research-program step and its explicit orchestration prerequisites."""

    experiment: FirstProgramExperiment
    title: str
    purpose: str
    depends_on: tuple[FirstProgramExperiment, ...]
    required_domains: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FirstProgramGrid:
    """Version 0.1 parameter families declared before historical execution."""

    trend_contexts: tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4", "T5", "T6")
    consolidation_durations: tuple[int, ...] = (10, 15, 20, 25, 30, 40, 50, 60)
    breakout_definitions: tuple[str, ...] = ("B1", "B2", "B3", "B4", "B5", "B6")
    forward_horizons: tuple[int, ...] = (5, 10, 20, 40, 60, 120, 252)
    fixed_stop_percentages: tuple[float, ...] = (0.02, 0.03, 0.04, 0.05, 0.07, 0.10)
    atr_stop_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0)


FIRST_RESEARCH_PROGRAM: tuple[ProgramStep, ...] = (
    ProgramStep(
        FirstProgramExperiment.A_TREND_BASELINE,
        "Trend-only baseline",
        "Quantify ordinary trend continuation before attributing performance to consolidation.",
        (),
        ("data", "universe", "features", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.B_DURATION,
        "Consolidation duration",
        "Map consolidation duration against forward outcomes without simultaneous tightness search.",
        (FirstProgramExperiment.A_TREND_BASELINE,),
        ("data", "features", "patterns", "events", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.C_TIGHTNESS,
        "Consolidation tightness",
        "Test range, ATR, and volatility compression within candidate duration regions.",
        (FirstProgramExperiment.B_DURATION,),
        ("features", "patterns", "events", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.D_BREAKOUT,
        "Breakout definition",
        "Compare breakout boundaries, confirmation rules, and execution consequences.",
        (FirstProgramExperiment.C_TIGHTNESS,),
        ("patterns", "events", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.E_VOLUME,
        "Volume confirmation",
        "Test whether volume adds incremental information after base and breakout definitions.",
        (FirstProgramExperiment.D_BREAKOUT,),
        ("features", "patterns", "events", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.F_REGIME,
        "Market regime",
        "Condition the frozen setup on index trend, market volatility, and VIX where supported.",
        (FirstProgramExperiment.E_VOLUME,),
        ("features", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.G_VOLATILITY_AGE,
        "Stock volatility and age",
        "Assess stock volatility and trading-history effects without hard-coding unvalidated filters.",
        (FirstProgramExperiment.F_REGIME,),
        ("features", "outcomes", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.H_STOPS,
        "Simple stop policies",
        "Compare no-stop, fixed, ATR, and structural policies on the frozen event population.",
        (FirstProgramExperiment.G_VOLATILITY_AGE,),
        ("outcomes", "risk", "statistics"),
    ),
    ProgramStep(
        FirstProgramExperiment.I_COMBINED_VALIDATION,
        "Combined candidate validation",
        "Freeze a compact candidate definition and challenge it on unseen data.",
        (FirstProgramExperiment.H_STOPS,),
        ("validation", "statistics", "risk"),
    ),
    ProgramStep(
        FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
        "Walk-forward and final holdout",
        "Assess temporal stability and make the final production-eligibility research decision.",
        (FirstProgramExperiment.I_COMBINED_VALIDATION,),
        ("validation", "statistics"),
    ),
)


def validate_first_research_program(
    steps: tuple[ProgramStep, ...] = FIRST_RESEARCH_PROGRAM,
) -> None:
    """Fail if the A-J plan is incomplete, duplicated, or topologically invalid."""

    expected = tuple(FirstProgramExperiment)
    observed = tuple(step.experiment for step in steps)
    if observed != expected:
        raise ValueError("first research program must contain the canonical ordered A-J sequence")

    completed: set[FirstProgramExperiment] = set()
    for step in steps:
        if not step.title.strip() or not step.purpose.strip():
            raise ValueError(f"experiment {step.experiment.value} has incomplete planning metadata")
        missing = set(step.depends_on) - completed
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ValueError(
                f"experiment {step.experiment.value} depends on incomplete prior experiments: {names}"
            )
        if not step.required_domains:
            raise ValueError(f"experiment {step.experiment.value} declares no required domains")
        completed.add(step.experiment)


def first_program_step(experiment: FirstProgramExperiment) -> ProgramStep:
    """Return planning metadata for one stable A-J experiment identifier."""

    return next(step for step in FIRST_RESEARCH_PROGRAM if step.experiment is experiment)
