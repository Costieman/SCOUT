"""Tests for versioned executable Experiment A-J templates."""

from __future__ import annotations

from trade_scout.experiments.contracts import JSONValue, ResearchMode
from trade_scout.experiments.first_research_program import FirstProgramExperiment
from trade_scout.experiments.first_program_templates import (
    FIRST_PROGRAM_TEMPLATES,
    FirstProgramRuntime,
    dry_run_first_program_experiment,
    first_program_template,
    validate_first_program_templates,
)


def _runtime(
    experiment: FirstProgramExperiment,
    *,
    resolved_values: dict[str, JSONValue] | None = None,
    completed: frozenset[FirstProgramExperiment] | None = None,
    final_holdout_uninspected: bool = True,
) -> FirstProgramRuntime:
    template = first_program_template(experiment)
    return FirstProgramRuntime(
        dataset_version="synthetic-template-test-v1",
        universe_version="point-in-time-test-v1",
        code_version="test-code-sha",
        config_schema_version="experiment-config-v0.1",
        available_capabilities=frozenset(template.required_capabilities),
        completed_experiments=completed or frozenset(),
        resolved_values=resolved_values,
        final_holdout_uninspected=final_holdout_uninspected,
    )


def test_templates_cover_canonical_a_j_sequence_with_governed_modes() -> None:
    validate_first_program_templates()

    assert tuple(item.experiment for item in FIRST_PROGRAM_TEMPLATES) == tuple(
        FirstProgramExperiment
    )
    assert all(item.mode is ResearchMode.EXPLORATORY for item in FIRST_PROGRAM_TEMPLATES[:8])
    assert all(item.mode is ResearchMode.CONFIRMATORY for item in FIRST_PROGRAM_TEMPLATES[8:])


def test_experiment_a_materializes_declared_trend_by_horizon_search_space() -> None:
    plan = dry_run_first_program_experiment(
        FirstProgramExperiment.A_TREND_BASELINE,
        _runtime(FirstProgramExperiment.A_TREND_BASELINE),
    )

    assert plan.ready is True
    assert plan.batch_plan is not None
    assert plan.batch_plan.run_count == 7 * 7
    assert plan.parameter_grid["variables.trend_context"] == (
        "T0",
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
    )
    assert plan.parameter_grid["variables.forward_horizon"] == (5, 10, 20, 40, 60, 120, 252)


def test_duration_template_blocks_until_prior_evidence_and_fixed_inputs_exist() -> None:
    blocked = dry_run_first_program_experiment(
        FirstProgramExperiment.B_DURATION,
        _runtime(FirstProgramExperiment.B_DURATION),
    )

    assert blocked.ready is False
    assert "prior experiments incomplete: A" in blocked.blockers
    assert "unresolved research input: selected_trend_contexts" in blocked.blockers
    assert "unresolved research input: fixed_tightness_definition" in blocked.blockers

    resolved: dict[str, JSONValue] = {
        "selected_trend_contexts": ["T1", "T2"],
        "fixed_tightness_definition": {"kind": "range_pct", "max_range_pct": 0.12},
    }
    ready = dry_run_first_program_experiment(
        FirstProgramExperiment.B_DURATION,
        _runtime(
            FirstProgramExperiment.B_DURATION,
            completed=frozenset({FirstProgramExperiment.A_TREND_BASELINE}),
            resolved_values=resolved,
        ),
    )

    assert ready.ready is True
    assert ready.batch_plan is not None
    assert ready.batch_plan.run_count == 8 * 7


def test_tightness_and_breakout_thresholds_remain_explicit_dynamic_variants() -> None:
    tightness = first_program_template(FirstProgramExperiment.C_TIGHTNESS)
    breakout = first_program_template(FirstProgramExperiment.D_BREAKOUT)

    assert tightness.dynamic_parameter_grids == {
        "variables.tightness_variant": "tightness_variants"
    }
    assert breakout.dynamic_parameter_grids == {"variables.breakout_variant": "breakout_variants"}
    assert "tightness_variants" in tightness.required_resolution_keys
    assert "breakout_variants" in breakout.required_resolution_keys


def test_experiment_h_preserves_simple_stop_family_search_space() -> None:
    template = first_program_template(FirstProgramExperiment.H_STOPS)
    stop_grid = template.static_parameter_grid["variables.stop_policy"]

    assert "no_stop" in stop_grid
    assert "fixed_2pct" in stop_grid
    assert "fixed_10pct" in stop_grid
    assert "atr_1x" in stop_grid
    assert "atr_3x" in stop_grid
    assert "structural_base_low" in stop_grid
    assert "structural_boundary_buffered" in stop_grid
    assert "hybrid_structural_atr" in stop_grid


def test_confirmatory_i_has_no_search_grid_and_requires_frozen_validation_inputs() -> None:
    completed = frozenset(item for item in FirstProgramExperiment if item.value <= "H")
    resolved: dict[str, JSONValue] = {
        "frozen_candidate_definition": {"candidate_id": "candidate-v1"},
        "frozen_primary_outcome": {"metric": "forward_return", "horizon": 20},
        "frozen_comparator": "same_trend_without_target_pattern",
        "unseen_validation_period": {"start": "2020-01-01", "end": "2022-12-31"},
        "frozen_risk_policy_candidates": ["no_stop", "atr_2x"],
    }
    plan = dry_run_first_program_experiment(
        FirstProgramExperiment.I_COMBINED_VALIDATION,
        _runtime(
            FirstProgramExperiment.I_COMBINED_VALIDATION,
            completed=completed,
            resolved_values=resolved,
        ),
    )

    assert plan.ready is True
    assert plan.definition is not None
    assert plan.definition.mode is ResearchMode.CONFIRMATORY
    assert plan.parameter_grid == {}
    assert plan.batch_plan is not None and plan.batch_plan.run_count == 1


def test_final_holdout_cannot_be_reused_after_inspection() -> None:
    completed = frozenset(
        item
        for item in FirstProgramExperiment
        if item is not FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT
    )
    resolved: dict[str, JSONValue] = {
        "frozen_candidate_definition": {"candidate_id": "candidate-v1"},
        "frozen_primary_outcome": {"metric": "forward_return", "horizon": 20},
        "frozen_comparator": "same_trend_without_target_pattern",
        "walk_forward_plan": {"folds": "time_ordered"},
        "final_holdout_period": {"start": "2023-01-01", "end": "2025-12-31"},
        "promotion_criteria": {"status": "predeclared"},
    }
    plan = dry_run_first_program_experiment(
        FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
        _runtime(
            FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
            completed=completed,
            resolved_values=resolved,
            final_holdout_uninspected=False,
        ),
    )

    assert plan.ready is False
    assert any("final holdout has already been inspected" in item for item in plan.blockers)
