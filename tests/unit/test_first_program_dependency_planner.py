"""Tests for the concrete first-program dependency planner."""

from __future__ import annotations

from dataclasses import replace

from trade_scout.experiments.dependency_planner import (
    DependencyCategory,
    ResearchDependencyInventory,
    first_program_dependency_requirements,
    preflight_first_program_dependencies,
)
from trade_scout.experiments.first_program_templates import (
    FirstProgramRuntime,
    first_program_template,
)
from trade_scout.experiments.first_research_program import FirstProgramExperiment


def _runtime(
    experiment: FirstProgramExperiment,
    *,
    completed: frozenset[FirstProgramExperiment] = frozenset(),
    resolved_values: dict[str, object] | None = None,
    final_holdout_uninspected: bool = True,
) -> FirstProgramRuntime:
    template = first_program_template(experiment)
    return FirstProgramRuntime(
        dataset_version="dataset-v1",
        universe_version="universe-v1",
        code_version="code-sha",
        config_schema_version="config-v1",
        available_capabilities=frozenset(template.required_capabilities),
        completed_experiments=completed,
        resolved_values=resolved_values,  # type: ignore[arg-type]
        final_holdout_uninspected=final_holdout_uninspected,
    )


def _complete_inventory(
    experiment: FirstProgramExperiment,
    runtime: FirstProgramRuntime,
) -> ResearchDependencyInventory:
    requirements = first_program_dependency_requirements(experiment, runtime)

    def ids(category: DependencyCategory) -> frozenset[str]:
        return frozenset(item.requirement_id for item in requirements if item.category is category)

    return ResearchDependencyInventory(
        dataset_versions=ids(DependencyCategory.DATASET),
        universe_versions=ids(DependencyCategory.UNIVERSE),
        feature_definitions=ids(DependencyCategory.FEATURE),
        event_definitions=ids(DependencyCategory.EVENT),
        outcome_horizons=frozenset(int(value) for value in ids(DependencyCategory.OUTCOME_HORIZON)),
        risk_policy_ids=ids(DependencyCategory.RISK_POLICY),
        comparator_ids=ids(DependencyCategory.COMPARATOR),
        validation_plan_ids=ids(DependencyCategory.VALIDATION_PLAN),
        assumption_ids=ids(DependencyCategory.ASSUMPTION),
        capabilities=ids(DependencyCategory.CAPABILITY),
        completed_experiments=frozenset(
            FirstProgramExperiment(value) for value in ids(DependencyCategory.PRIOR_EXPERIMENT)
        ),
    )


def test_experiment_a_requires_exact_versions_features_horizons_and_comparator() -> None:
    runtime = _runtime(FirstProgramExperiment.A_TREND_BASELINE)
    inventory = _complete_inventory(FirstProgramExperiment.A_TREND_BASELINE, runtime)

    result = preflight_first_program_dependencies(
        FirstProgramExperiment.A_TREND_BASELINE,
        runtime,
        inventory,
    )

    assert result.ready is True
    assert result.template_dry_run.batch_plan is not None
    assert result.template_dry_run.batch_plan.run_count == 49
    assert "trend_contexts_t0_t6" in inventory.feature_definitions
    assert inventory.outcome_horizons == frozenset({5, 10, 20, 40, 60, 120, 252})
    assert inventory.comparator_ids == frozenset({"unconditional_eligible_universe"})


def test_dataset_version_mismatch_and_missing_horizon_fail_closed() -> None:
    runtime = _runtime(FirstProgramExperiment.A_TREND_BASELINE)
    inventory = _complete_inventory(FirstProgramExperiment.A_TREND_BASELINE, runtime)
    broken = replace(
        inventory,
        dataset_versions=frozenset({"different-dataset"}),
        outcome_horizons=inventory.outcome_horizons - {252},
    )

    result = preflight_first_program_dependencies(
        FirstProgramExperiment.A_TREND_BASELINE,
        runtime,
        broken,
    )

    assert result.ready is False
    assert "missing dataset: dataset-v1" in result.blockers
    assert "missing outcome_horizon: 252" in result.blockers


def test_duration_preflight_checks_concrete_feature_and_event_dependencies() -> None:
    experiment = FirstProgramExperiment.B_DURATION
    runtime = _runtime(
        experiment,
        completed=frozenset({FirstProgramExperiment.A_TREND_BASELINE}),
        resolved_values={
            "selected_trend_contexts": ["T1", "T2"],
            "fixed_tightness_definition": {"kind": "range_pct", "max_range_pct": 0.12},
        },
    )
    inventory = _complete_inventory(experiment, runtime)
    broken = replace(
        inventory,
        event_definitions=frozenset(),
        feature_definitions=inventory.feature_definitions - {"consolidation_compression"},
    )

    result = preflight_first_program_dependencies(experiment, runtime, broken)

    assert result.ready is False
    missing = {(item.category, item.requirement_id) for item in result.missing_requirements}
    assert (DependencyCategory.EVENT, "consolidation_breakout") in missing
    assert (DependencyCategory.FEATURE, "consolidation_compression") in missing


def test_stop_experiment_requires_full_simple_policy_surface_on_same_preflight() -> None:
    experiment = FirstProgramExperiment.H_STOPS
    completed = frozenset(item for item in FirstProgramExperiment if item.value < "H")
    runtime = _runtime(
        experiment,
        completed=completed,
        resolved_values={
            "frozen_event_definition": {"event_id": "candidate-event-v1"},
            "cost_assumptions": {"entry_bps": 5, "exit_bps": 5},
        },
    )
    inventory = _complete_inventory(experiment, runtime)
    assert "hybrid_structural_atr" in inventory.risk_policy_ids
    broken = replace(
        inventory,
        risk_policy_ids=inventory.risk_policy_ids - {"hybrid_structural_atr"},
    )

    result = preflight_first_program_dependencies(experiment, runtime, broken)

    assert result.ready is False
    assert "missing risk_policy: hybrid_structural_atr" in result.blockers


def test_combined_validation_requires_frozen_horizon_comparator_risk_and_validation_plan() -> None:
    experiment = FirstProgramExperiment.I_COMBINED_VALIDATION
    completed = frozenset(item for item in FirstProgramExperiment if item.value <= "H")
    runtime = _runtime(
        experiment,
        completed=completed,
        resolved_values={
            "frozen_candidate_definition": {"candidate_id": "candidate-v1"},
            "frozen_primary_outcome": {"metric": "forward_return", "horizon": 20},
            "frozen_comparator": "same_trend_without_target_pattern",
            "unseen_validation_period": {"start": "2020-01-01", "end": "2022-12-31"},
            "frozen_risk_policy_candidates": ["no_stop", "atr_2x"],
        },
    )
    inventory = _complete_inventory(experiment, runtime)

    result = preflight_first_program_dependencies(experiment, runtime, inventory)

    assert result.ready is True
    assert inventory.outcome_horizons == frozenset({20})
    assert inventory.comparator_ids == frozenset({"same_trend_without_target_pattern"})
    assert inventory.risk_policy_ids == frozenset({"no_stop", "atr_2x"})
    assert "validation_period_unseen_during_selection" in inventory.validation_plan_ids

    missing_validation = replace(
        inventory,
        validation_plan_ids=(
            inventory.validation_plan_ids - {"validation_period_unseen_during_selection"}
        ),
    )
    blocked = preflight_first_program_dependencies(experiment, runtime, missing_validation)
    assert blocked.ready is False
    assert any("missing validation_plan" in item for item in blocked.blockers)


def test_final_holdout_template_guard_survives_concrete_dependency_readiness() -> None:
    experiment = FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT
    completed = frozenset(
        item
        for item in FirstProgramExperiment
        if item is not FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT
    )
    runtime = _runtime(
        experiment,
        completed=completed,
        resolved_values={
            "frozen_candidate_definition": {"candidate_id": "candidate-v1"},
            "frozen_primary_outcome": {"metric": "forward_return", "horizon": 20},
            "frozen_comparator": "same_trend_without_target_pattern",
            "walk_forward_plan": {"folds": "time_ordered"},
            "final_holdout_period": {"start": "2023-01-01", "end": "2025-12-31"},
            "promotion_criteria": {"status": "predeclared"},
        },
        final_holdout_uninspected=False,
    )
    inventory = _complete_inventory(experiment, runtime)

    result = preflight_first_program_dependencies(experiment, runtime, inventory)

    assert result.ready is False
    assert any("final holdout has already been inspected" in item for item in result.blockers)


def test_inventory_checksum_changes_when_declared_resources_change() -> None:
    runtime = _runtime(FirstProgramExperiment.A_TREND_BASELINE)
    inventory = _complete_inventory(FirstProgramExperiment.A_TREND_BASELINE, runtime)
    first = preflight_first_program_dependencies(
        FirstProgramExperiment.A_TREND_BASELINE,
        runtime,
        inventory,
    )
    changed = replace(inventory, assumption_ids=inventory.assumption_ids | {"extra-assumption"})
    second = preflight_first_program_dependencies(
        FirstProgramExperiment.A_TREND_BASELINE,
        runtime,
        changed,
    )

    assert first.requirements_checksum == second.requirements_checksum
    assert first.inventory_checksum != second.inventory_checksum
