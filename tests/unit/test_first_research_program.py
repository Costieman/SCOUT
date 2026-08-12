"""Tests for the machine-readable first research-program plan."""

from __future__ import annotations

from dataclasses import replace

import pytest

from trade_scout.experiments.first_research_program import (
    FIRST_RESEARCH_PROGRAM,
    FirstProgramExperiment,
    FirstProgramGrid,
    first_program_step,
    validate_first_research_program,
)


def test_first_program_is_complete_and_ordered() -> None:
    validate_first_research_program()
    assert tuple(step.experiment for step in FIRST_RESEARCH_PROGRAM) == tuple(FirstProgramExperiment)


def test_first_program_grid_preserves_declared_v01_search_families() -> None:
    grid = FirstProgramGrid()
    assert grid.consolidation_durations == (10, 15, 20, 25, 30, 40, 50, 60)
    assert grid.forward_horizons == (5, 10, 20, 40, 60, 120, 252)
    assert grid.fixed_stop_percentages == (0.02, 0.03, 0.04, 0.05, 0.07, 0.10)
    assert grid.atr_stop_multiples == (1.0, 1.5, 2.0, 2.5, 3.0)


def test_stop_experiment_cannot_precede_its_required_research_sequence() -> None:
    reordered = (
        FIRST_RESEARCH_PROGRAM[0],
        FIRST_RESEARCH_PROGRAM[7],
        *FIRST_RESEARCH_PROGRAM[1:7],
        *FIRST_RESEARCH_PROGRAM[8:],
    )
    with pytest.raises(ValueError, match="canonical ordered A-J sequence"):
        validate_first_research_program(reordered)


def test_missing_dependency_is_rejected() -> None:
    broken = list(FIRST_RESEARCH_PROGRAM)
    broken[1] = replace(
        broken[1],
        depends_on=(FirstProgramExperiment.C_TIGHTNESS,),
    )
    with pytest.raises(ValueError, match="depends on incomplete prior experiments"):
        validate_first_research_program(tuple(broken))


def test_lookup_returns_declared_step() -> None:
    step = first_program_step(FirstProgramExperiment.H_STOPS)
    assert step.title == "Simple stop policies"
    assert "risk" in step.required_domains
