"""Versioned executable templates for the first consolidation-breakout research program.

The accepted First Research Program defines the controlled A-J sequence but intentionally leaves
several exploratory thresholds to be resolved from prior evidence. This module preserves that
scientific boundary: source-defined grids are executable immediately, while unspecified thresholds
remain explicit preflight blockers rather than being invented in code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from trade_scout.experiments.contracts import ExperimentDefinition, JSONValue, ResearchMode
from trade_scout.experiments.first_research_program import (
    FIRST_RESEARCH_PROGRAM,
    FirstProgramExperiment,
    FirstProgramGrid,
    first_program_step,
)
from trade_scout.experiments.planner import ExperimentBatchPlan, plan_experiment_batch

FIRST_PROGRAM_TEMPLATE_VERSION = "first-research-program-templates-v0.1"
FIRST_PROGRAM_ID = "consolidation-breakouts-v0.1"


@dataclass(frozen=True, slots=True)
class FirstProgramTemplate:
    """One reusable A-J experiment template before dataset-specific execution."""

    experiment: FirstProgramExperiment
    title: str
    mode: ResearchMode
    hypothesis: str
    hypothesis_family_id: str
    required_capabilities: tuple[str, ...]
    required_resolution_keys: tuple[str, ...]
    comparators: tuple[str, ...]
    primary_outcomes: tuple[str, ...]
    validation_requirements: tuple[str, ...]
    base_variables: Mapping[str, JSONValue]
    static_parameter_grid: Mapping[str, tuple[JSONValue, ...]]
    dynamic_parameter_grids: Mapping[str, str]
    template_version: str = FIRST_PROGRAM_TEMPLATE_VERSION

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.hypothesis.strip():
            raise ValueError("first-program template title and hypothesis must be non-empty")
        if not self.hypothesis_family_id.strip() or not self.template_version.strip():
            raise ValueError("first-program template identity/version must be non-empty")
        if len(set(self.required_resolution_keys)) != len(self.required_resolution_keys):
            raise ValueError("template resolution keys must be unique")
        overlap = set(self.static_parameter_grid) & set(self.dynamic_parameter_grids)
        if overlap:
            raise ValueError("static and dynamic parameter grids must use different paths")


@dataclass(frozen=True, slots=True)
class FirstProgramRuntime:
    """Dataset/code context and prior decisions supplied to one template dry run."""

    dataset_version: str
    universe_version: str
    code_version: str
    config_schema_version: str
    available_capabilities: frozenset[str]
    completed_experiments: frozenset[FirstProgramExperiment] = frozenset()
    resolved_values: Mapping[str, JSONValue] | None = None
    parent_experiment_id: str | None = None
    final_holdout_uninspected: bool = True

    def __post_init__(self) -> None:
        required = (
            self.dataset_version,
            self.universe_version,
            self.code_version,
            self.config_schema_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("first-program runtime versions must be non-empty")


@dataclass(frozen=True, slots=True)
class FirstProgramDryRun:
    """Preflight result for one template, including the executable batch when ready."""

    template: FirstProgramTemplate
    blockers: tuple[str, ...]
    definition: ExperimentDefinition | None
    batch_plan: ExperimentBatchPlan | None
    required_capabilities: tuple[str, ...]
    parameter_grid: Mapping[str, tuple[JSONValue, ...]]

    @property
    def ready(self) -> bool:
        """Return whether the template can be executed without inventing missing research inputs."""

        return not self.blockers and self.definition is not None and self.batch_plan is not None


_GRID = FirstProgramGrid()
_OUTCOMES = (
    "forward_return",
    "benchmark_relative_return",
    "positive_return_probability",
    "mae",
    "mfe",
    "max_drawdown",
    "time_to_mae",
    "time_to_mfe",
)
_BASE_COMPARATORS = (
    "unconditional_eligible_universe",
    "same_trend_without_target_pattern",
)


def _template(
    experiment: FirstProgramExperiment,
    *,
    mode: ResearchMode,
    hypothesis: str,
    required_capabilities: tuple[str, ...],
    required_resolution_keys: tuple[str, ...] = (),
    comparators: tuple[str, ...] = _BASE_COMPARATORS,
    primary_outcomes: tuple[str, ...] = _OUTCOMES,
    validation_requirements: tuple[str, ...] = (),
    base_variables: Mapping[str, JSONValue] | None = None,
    static_parameter_grid: Mapping[str, tuple[JSONValue, ...]] | None = None,
    dynamic_parameter_grids: Mapping[str, str] | None = None,
) -> FirstProgramTemplate:
    step = first_program_step(experiment)
    return FirstProgramTemplate(
        experiment=experiment,
        title=step.title,
        mode=mode,
        hypothesis=hypothesis,
        hypothesis_family_id=f"{FIRST_PROGRAM_ID}:{experiment.value}",
        required_capabilities=required_capabilities,
        required_resolution_keys=required_resolution_keys,
        comparators=comparators,
        primary_outcomes=primary_outcomes,
        validation_requirements=validation_requirements,
        base_variables=base_variables or {},
        static_parameter_grid=static_parameter_grid or {},
        dynamic_parameter_grids=dynamic_parameter_grids or {},
    )


FIRST_PROGRAM_TEMPLATES: tuple[FirstProgramTemplate, ...] = (
    _template(
        FirstProgramExperiment.A_TREND_BASELINE,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Forward outcome distributions differ across the declared T0-T6 trend contexts; "
            "quantifying them establishes the baseline before consolidation is credited with edge."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "point_in_time_universe",
            "trend_contexts_t0_t6",
            "outcome_path_measurement",
            "comparator_statistics",
        ),
        comparators=("unconditional_eligible_universe",),
        base_variables={"trend_context": "T0", "forward_horizon": 5},
        static_parameter_grid={
            "variables.trend_context": tuple(_GRID.trend_contexts),
            "variables.forward_horizon": tuple(_GRID.forward_horizons),
        },
    ),
    _template(
        FirstProgramExperiment.B_DURATION,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Consolidation duration may contain information about post-breakout outcomes when "
            "tightness and a small selected set of trend contexts are held fixed."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "point_in_time_universe",
            "trend_features",
            "consolidation_pattern",
            "breakout_events",
            "outcome_path_measurement",
            "comparator_statistics",
        ),
        required_resolution_keys=("selected_trend_contexts", "fixed_tightness_definition"),
        base_variables={"duration_sessions": 10, "forward_horizon": 5},
        static_parameter_grid={
            "variables.duration_sessions": tuple(_GRID.consolidation_durations),
            "variables.forward_horizon": tuple(_GRID.forward_horizons),
        },
    ),
    _template(
        FirstProgramExperiment.C_TIGHTNESS,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Within broad candidate duration regions, consolidation compression may change the "
            "post-breakout outcome distribution."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "consolidation_pattern",
            "atr_features",
            "realized_volatility_features",
            "breakout_events",
            "outcome_path_measurement",
            "parameter_surface_statistics",
        ),
        required_resolution_keys=("candidate_duration_regions", "tightness_variants"),
        base_variables={"tightness_variant": {}, "forward_horizon": 5},
        static_parameter_grid={"variables.forward_horizon": tuple(_GRID.forward_horizons)},
        dynamic_parameter_grids={"variables.tightness_variant": "tightness_variants"},
        validation_requirements=("sample_size_surface_alongside_parameter_surface",),
    ),
    _template(
        FirstProgramExperiment.D_BREAKOUT,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Breakout boundary and confirmation definitions may change signal frequency, entry "
            "consequences, and forward expectancy after the base structure is held fixed."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "consolidation_pattern",
            "breakout_event_families_b1_b6",
            "atr_features",
            "outcome_path_measurement",
            "comparator_statistics",
        ),
        required_resolution_keys=("frozen_base_definition", "breakout_variants"),
        base_variables={"breakout_variant": {}, "forward_horizon": 5},
        static_parameter_grid={"variables.forward_horizon": tuple(_GRID.forward_horizons)},
        dynamic_parameter_grids={"variables.breakout_variant": "breakout_variants"},
        comparators=("simpler_breakout_definitions", "same_trend_without_target_pattern"),
    ),
    _template(
        FirstProgramExperiment.E_VOLUME,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Volume confirmation may add incremental information after controlling for the selected "
            "base and breakout definitions, but any gain must be weighed against sample-size cost."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "volume_features",
            "frozen_base_and_breakout_events",
            "outcome_path_measurement",
            "comparator_statistics",
        ),
        required_resolution_keys=("frozen_base_breakout_definition", "volume_variants"),
        base_variables={"volume_variant": {}, "forward_horizon": 5},
        static_parameter_grid={"variables.forward_horizon": tuple(_GRID.forward_horizons)},
        dynamic_parameter_grids={"variables.volume_variant": "volume_variants"},
        comparators=("no_volume_filter",),
    ),
    _template(
        FirstProgramExperiment.F_REGIME,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Broad market regime may alter calibration of the frozen setup; conditioning should be "
            "retained only when it adds information without merely fragmenting the sample."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "frozen_event_set",
            "benchmark_index_trend",
            "market_realized_volatility",
            "vix_history",
            "outcome_path_measurement",
            "subgroup_statistics",
        ),
        required_resolution_keys=("frozen_setup_definition", "regime_variants"),
        base_variables={"regime_variant": {}, "forward_horizon": 5},
        static_parameter_grid={"variables.forward_horizon": tuple(_GRID.forward_horizons)},
        dynamic_parameter_grids={"variables.regime_variant": "regime_variants"},
        comparators=("unconditioned_frozen_setup",),
    ),
    _template(
        FirstProgramExperiment.G_VOLATILITY_AGE,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Stock volatility and trading age may alter continuation and risk distributions, but "
            "hard filters require independent out-of-sample evidence."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "frozen_event_set",
            "atr_percentage",
            "realized_volatility",
            "trading_age",
            "market_volatility",
            "outcome_path_measurement",
            "subgroup_statistics",
        ),
        required_resolution_keys=("frozen_setup_definition", "stock_conditioning_variants"),
        base_variables={"conditioning_variant": {}, "forward_horizon": 5},
        static_parameter_grid={"variables.forward_horizon": tuple(_GRID.forward_horizons)},
        dynamic_parameter_grids={"variables.conditioning_variant": "stock_conditioning_variants"},
        comparators=("unconditioned_frozen_setup",),
    ),
    _template(
        FirstProgramExperiment.H_STOPS,
        mode=ResearchMode.EXPLORATORY,
        hypothesis=(
            "Simple protective-stop families may improve net expectancy or tail behavior on the "
            "same frozen event population without redefining event membership."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "frozen_event_set",
            "outcome_path_measurement",
            "risk_policy_comparison_harness",
            "cost_model",
        ),
        required_resolution_keys=("frozen_event_definition", "cost_assumptions"),
        primary_outcomes=(
            "net_expectancy",
            "win_probability",
            "profit_factor",
            "r_multiple_distribution",
            "premature_stop_rate",
            "gap_through_stop_frequency",
            "tail_loss",
            "holding_period",
            "mae_before_exit",
            "mfe_after_entry",
        ),
        comparators=("no_stop_baseline",),
        base_variables={"stop_policy": "no_stop", "forward_horizon": 20},
        static_parameter_grid={
            "variables.stop_policy": (
                "no_stop",
                *tuple(f"fixed_{int(value * 100)}pct" for value in _GRID.fixed_stop_percentages),
                *tuple(f"atr_{value:g}x" for value in _GRID.atr_stop_multiples),
                "structural_base_low",
                "structural_boundary_buffered",
                "hybrid_structural_atr",
            ),
        },
    ),
    _template(
        FirstProgramExperiment.I_COMBINED_VALIDATION,
        mode=ResearchMode.CONFIRMATORY,
        hypothesis=(
            "A compact candidate definition frozen from prior exploratory evidence retains its "
            "predeclared comparator-adjusted effect on unseen validation data."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "frozen_candidate_definition",
            "outcome_path_measurement",
            "comparator_statistics",
            "validation_engine",
            "robustness_engine",
        ),
        required_resolution_keys=(
            "frozen_candidate_definition",
            "frozen_primary_outcome",
            "frozen_comparator",
            "unseen_validation_period",
            "frozen_risk_policy_candidates",
        ),
        base_variables={},
        validation_requirements=(
            "entry_conditions_frozen",
            "primary_outcome_frozen",
            "comparator_frozen",
            "validation_period_unseen_during_selection",
            "robustness_stress_tests_predeclared",
        ),
    ),
    _template(
        FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
        mode=ResearchMode.CONFIRMATORY,
        hypothesis=(
            "The frozen candidate remains stable across time-ordered walk-forward folds and the "
            "reserved final holdout, supporting an explicit production-eligibility decision."
        ),
        required_capabilities=(
            "canonical_research_bars",
            "frozen_candidate_definition",
            "validation_engine",
            "walk_forward_engine",
            "robustness_engine",
            "decision_governance",
        ),
        required_resolution_keys=(
            "frozen_candidate_definition",
            "frozen_primary_outcome",
            "frozen_comparator",
            "walk_forward_plan",
            "final_holdout_period",
            "promotion_criteria",
        ),
        base_variables={},
        validation_requirements=(
            "time_ordered_walk_forward",
            "final_holdout_reserved",
            "final_holdout_not_repeatedly_inspected",
            "nearby_parameter_robustness",
            "higher_cost_stress",
            "explicit_promote_reject_or_return_decision",
        ),
    ),
)


def first_program_template(experiment: FirstProgramExperiment) -> FirstProgramTemplate:
    """Return the canonical versioned template for one A-J experiment."""

    return next(item for item in FIRST_PROGRAM_TEMPLATES if item.experiment is experiment)


def validate_first_program_templates() -> None:
    """Validate one template per canonical A-J program step and governance mode."""

    expected = tuple(step.experiment for step in FIRST_RESEARCH_PROGRAM)
    observed = tuple(item.experiment for item in FIRST_PROGRAM_TEMPLATES)
    if observed != expected:
        raise ValueError("first-program templates must contain the canonical ordered A-J sequence")
    for template in FIRST_PROGRAM_TEMPLATES:
        step = first_program_step(template.experiment)
        if template.title != step.title:
            raise ValueError(f"template {template.experiment.value} title differs from program step")
        if template.experiment.value <= "H" and template.mode is not ResearchMode.EXPLORATORY:
            raise ValueError("experiments A-H must remain exploratory templates")
        if template.experiment.value in {"I", "J"} and template.mode is not ResearchMode.CONFIRMATORY:
            raise ValueError("experiments I-J must remain confirmatory templates")


def dry_run_first_program_experiment(
    experiment: FirstProgramExperiment,
    runtime: FirstProgramRuntime,
) -> FirstProgramDryRun:
    """Resolve one template into an executable batch plan or explicit scientific blockers."""

    template = first_program_template(experiment)
    step = first_program_step(experiment)
    resolved = dict(runtime.resolved_values or {})
    blockers: list[str] = []

    missing_dependencies = tuple(
        item for item in step.depends_on if item not in runtime.completed_experiments
    )
    if missing_dependencies:
        labels = ", ".join(item.value for item in missing_dependencies)
        blockers.append(f"prior experiments incomplete: {labels}")

    missing_capabilities = tuple(
        capability
        for capability in template.required_capabilities
        if capability not in runtime.available_capabilities
    )
    blockers.extend(f"missing capability: {item}" for item in missing_capabilities)

    for key in template.required_resolution_keys:
        if key not in resolved:
            blockers.append(f"unresolved research input: {key}")

    parameter_grid: dict[str, tuple[JSONValue, ...]] = {
        path: tuple(values) for path, values in template.static_parameter_grid.items()
    }
    for path, resolution_key in template.dynamic_parameter_grids.items():
        value = resolved.get(resolution_key)
        if value is None:
            continue
        if not isinstance(value, list) or not value:
            blockers.append(
                f"resolved research input {resolution_key} must be a non-empty list of variants"
            )
            continue
        parameter_grid[path] = tuple(value)

    if experiment is FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT:
        if not runtime.final_holdout_uninspected:
            blockers.append("final holdout has already been inspected; do not reuse it as final holdout")

    if blockers:
        return FirstProgramDryRun(
            template=template,
            blockers=tuple(blockers),
            definition=None,
            batch_plan=None,
            required_capabilities=template.required_capabilities,
            parameter_grid=parameter_grid,
        )

    configuration: dict[str, JSONValue] = {
        "research_program": {
            "program_id": FIRST_PROGRAM_ID,
            "program_version": "0.1",
            "experiment": experiment.value,
            "template_version": template.template_version,
        },
        "variables": dict(template.base_variables),
        "resolved_inputs": resolved,
        "comparators": list(template.comparators),
        "primary_outcomes": list(template.primary_outcomes),
        "validation_requirements": list(template.validation_requirements),
        "declared_search_space": {
            path: list(values) for path, values in parameter_grid.items()
        },
    }
    definition = ExperimentDefinition(
        name=f"first-program-{experiment.value.lower()}-{template.title.lower().replace(' ', '-')}",
        hypothesis=template.hypothesis,
        mode=template.mode,
        dataset_version=runtime.dataset_version,
        universe_version=runtime.universe_version,
        code_version=runtime.code_version,
        config_schema_version=runtime.config_schema_version,
        resolved_configuration=configuration,
        hypothesis_family_id=template.hypothesis_family_id,
        parent_experiment_id=runtime.parent_experiment_id,
    )
    batch_plan = plan_experiment_batch(definition, parameter_grid)
    return FirstProgramDryRun(
        template=template,
        blockers=(),
        definition=definition,
        batch_plan=batch_plan,
        required_capabilities=template.required_capabilities,
        parameter_grid=parameter_grid,
    )


__all__ = [
    "FIRST_PROGRAM_ID",
    "FIRST_PROGRAM_TEMPLATE_VERSION",
    "FIRST_PROGRAM_TEMPLATES",
    "FirstProgramDryRun",
    "FirstProgramRuntime",
    "FirstProgramTemplate",
    "dry_run_first_program_experiment",
    "first_program_template",
    "validate_first_program_templates",
]
