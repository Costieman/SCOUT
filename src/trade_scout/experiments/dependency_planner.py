"""Concrete dependency preflight for the first Trade Scout research program.

The template layer declares what an experiment means. This module answers the separate operational
question: are the exact dataset, universe, features, event definitions, horizons, risk policies,
comparators, validation plans, and research assumptions available to execute that template now?
Missing dependencies are reported; they are never silently substituted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.experiments.first_program_templates import (
    FirstProgramDryRun,
    FirstProgramRuntime,
    FirstProgramTemplate,
    dry_run_first_program_experiment,
    first_program_template,
)
from trade_scout.experiments.first_research_program import (
    FirstProgramExperiment,
    first_program_step,
)
from trade_scout.experiments.serialization import sha256_json

DEPENDENCY_PLANNER_VERSION = "first-program-dependency-planner-v0.1"


class DependencyCategory(StrEnum):
    """Resource families checked before a research-program experiment can execute."""

    DATASET = "dataset"
    UNIVERSE = "universe"
    FEATURE = "feature"
    EVENT = "event"
    OUTCOME_HORIZON = "outcome_horizon"
    RISK_POLICY = "risk_policy"
    COMPARATOR = "comparator"
    VALIDATION_PLAN = "validation_plan"
    ASSUMPTION = "assumption"
    CAPABILITY = "capability"
    PRIOR_EXPERIMENT = "prior_experiment"


@dataclass(frozen=True, slots=True)
class DependencyRequirement:
    """One named dependency required by a specific A-J experiment."""

    category: DependencyCategory
    requirement_id: str
    description: str

    def __post_init__(self) -> None:
        if not self.requirement_id.strip() or not self.description.strip():
            raise ValueError("dependency requirement identity and description must be non-empty")


@dataclass(frozen=True, slots=True)
class ResearchDependencyInventory:
    """Immutable declaration of concrete research resources currently available."""

    dataset_versions: frozenset[str] = frozenset()
    universe_versions: frozenset[str] = frozenset()
    feature_definitions: frozenset[str] = frozenset()
    event_definitions: frozenset[str] = frozenset()
    outcome_horizons: frozenset[int] = frozenset()
    risk_policy_ids: frozenset[str] = frozenset()
    comparator_ids: frozenset[str] = frozenset()
    validation_plan_ids: frozenset[str] = frozenset()
    assumption_ids: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    completed_experiments: frozenset[FirstProgramExperiment] = frozenset()

    def __post_init__(self) -> None:
        string_sets = (
            self.dataset_versions,
            self.universe_versions,
            self.feature_definitions,
            self.event_definitions,
            self.risk_policy_ids,
            self.comparator_ids,
            self.validation_plan_ids,
            self.assumption_ids,
            self.capabilities,
        )
        if any(any(not item.strip() for item in values) for values in string_sets):
            raise ValueError("dependency inventory string identifiers must be non-empty")
        if any(horizon < 1 for horizon in self.outcome_horizons):
            raise ValueError("dependency inventory horizons must be positive")


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    """Result of checking one dependency against the supplied inventory."""

    requirement: DependencyRequirement
    satisfied: bool
    evidence: str | None


@dataclass(frozen=True, slots=True)
class ResearchProgramDependencyPreflight:
    """Dry-run result combining scientific-template and concrete-resource readiness."""

    experiment: FirstProgramExperiment
    template_dry_run: FirstProgramDryRun
    requirements: tuple[DependencyRequirement, ...]
    checks: tuple[DependencyCheck, ...]
    blockers: tuple[str, ...]
    requirements_checksum: str
    inventory_checksum: str
    planner_version: str = DEPENDENCY_PLANNER_VERSION

    @property
    def ready(self) -> bool:
        """Return whether the experiment can execute without unresolved dependencies."""

        return (
            self.template_dry_run.ready
            and not self.blockers
            and all(check.satisfied for check in self.checks)
        )

    @property
    def missing_requirements(self) -> tuple[DependencyRequirement, ...]:
        """Return concrete dependencies that are absent from the supplied inventory."""

        return tuple(check.requirement for check in self.checks if not check.satisfied)


_COMMON_ASSUMPTIONS = (
    "no_future_information",
    "point_in_time_eligibility",
    "rule_based_exclusions",
    "explicit_entry_convention",
)

_FEATURE_REQUIREMENTS: dict[FirstProgramExperiment, tuple[str, ...]] = {
    FirstProgramExperiment.A_TREND_BASELINE: ("trend_contexts_t0_t6",),
    FirstProgramExperiment.B_DURATION: ("trend_features", "consolidation_compression"),
    FirstProgramExperiment.C_TIGHTNESS: (
        "atr_14",
        "realized_volatility",
        "compression_features",
    ),
    FirstProgramExperiment.D_BREAKOUT: ("atr_14",),
    FirstProgramExperiment.E_VOLUME: ("relative_volume",),
    FirstProgramExperiment.F_REGIME: (
        "benchmark_index_trend",
        "market_realized_volatility",
        "vix_history",
    ),
    FirstProgramExperiment.G_VOLATILITY_AGE: (
        "atr_percentage",
        "realized_volatility",
        "trading_age",
        "market_volatility",
    ),
    FirstProgramExperiment.H_STOPS: ("atr_14",),
}

_EVENT_REQUIREMENTS: dict[FirstProgramExperiment, tuple[str, ...]] = {
    FirstProgramExperiment.B_DURATION: ("consolidation_breakout",),
    FirstProgramExperiment.C_TIGHTNESS: ("consolidation_breakout",),
    FirstProgramExperiment.D_BREAKOUT: ("breakout_event_families_b1_b6",),
    FirstProgramExperiment.E_VOLUME: ("frozen_base_and_breakout_events",),
    FirstProgramExperiment.F_REGIME: ("frozen_event_set",),
    FirstProgramExperiment.G_VOLATILITY_AGE: ("frozen_event_set",),
    FirstProgramExperiment.H_STOPS: ("frozen_event_set",),
    FirstProgramExperiment.I_COMBINED_VALIDATION: ("frozen_candidate_definition",),
    FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT: ("frozen_candidate_definition",),
}

_H_STOP_POLICIES = (
    "no_stop",
    "fixed_2pct",
    "fixed_3pct",
    "fixed_4pct",
    "fixed_5pct",
    "fixed_7pct",
    "fixed_10pct",
    "atr_1x",
    "atr_1.5x",
    "atr_2x",
    "atr_2.5x",
    "atr_3x",
    "structural_base_low",
    "structural_boundary",
    "structural_boundary_buffered",
    "hybrid_structural_atr",
)


def first_program_dependency_requirements(
    experiment: FirstProgramExperiment,
    runtime: FirstProgramRuntime,
) -> tuple[DependencyRequirement, ...]:
    """Materialize the concrete dependency contract for one A-J experiment."""

    template = first_program_template(experiment)
    step = first_program_step(experiment)
    requirements: list[DependencyRequirement] = [
        _requirement(
            DependencyCategory.DATASET,
            runtime.dataset_version,
            "exact canonical dataset version selected by the experiment runtime",
        ),
        _requirement(
            DependencyCategory.UNIVERSE,
            runtime.universe_version,
            "exact point-in-time universe version selected by the experiment runtime",
        ),
    ]
    requirements.extend(
        _requirement(
            DependencyCategory.PRIOR_EXPERIMENT,
            dependency.value,
            f"completed prerequisite experiment {dependency.value}",
        )
        for dependency in step.depends_on
    )
    requirements.extend(
        _requirement(
            DependencyCategory.CAPABILITY,
            capability,
            f"analytical capability declared by Experiment {experiment.value}",
        )
        for capability in template.required_capabilities
    )
    requirements.extend(
        _requirement(
            DependencyCategory.FEATURE,
            feature,
            f"feature input required by Experiment {experiment.value}",
        )
        for feature in _FEATURE_REQUIREMENTS.get(experiment, ())
    )
    requirements.extend(
        _requirement(
            DependencyCategory.EVENT,
            event,
            f"event definition required by Experiment {experiment.value}",
        )
        for event in _EVENT_REQUIREMENTS.get(experiment, ())
    )
    requirements.extend(
        _requirement(
            DependencyCategory.OUTCOME_HORIZON,
            str(horizon),
            f"prespecified {horizon}-session outcome horizon",
        )
        for horizon in _required_horizons(template, runtime)
    )
    requirements.extend(
        _requirement(
            DependencyCategory.RISK_POLICY,
            policy,
            f"risk-policy definition required by Experiment {experiment.value}",
        )
        for policy in _required_risk_policies(experiment, runtime)
    )
    requirements.extend(
        _requirement(
            DependencyCategory.COMPARATOR,
            comparator,
            f"predeclared comparator required by Experiment {experiment.value}",
        )
        for comparator in _required_comparators(experiment, runtime, template)
    )
    requirements.extend(
        _requirement(
            DependencyCategory.VALIDATION_PLAN,
            validation,
            f"validation requirement declared by Experiment {experiment.value}",
        )
        for validation in template.validation_requirements
    )
    requirements.extend(
        _requirement(
            DependencyCategory.ASSUMPTION,
            assumption,
            "governing research-integrity assumption that must be explicitly accepted",
        )
        for assumption in _COMMON_ASSUMPTIONS
    )
    if experiment.value >= "H":
        requirements.append(
            _requirement(
                DependencyCategory.ASSUMPTION,
                "explicit_cost_model",
                "transaction-cost and slippage assumptions are explicit before interpretation",
            )
        )
    return _deduplicate_requirements(tuple(requirements))


def preflight_first_program_dependencies(
    experiment: FirstProgramExperiment,
    runtime: FirstProgramRuntime,
    inventory: ResearchDependencyInventory,
) -> ResearchProgramDependencyPreflight:
    """Dry-run one A-J experiment against both template and concrete dependency readiness."""

    template_dry_run = dry_run_first_program_experiment(experiment, runtime)
    requirements = first_program_dependency_requirements(experiment, runtime)
    checks = tuple(_check_requirement(requirement, inventory) for requirement in requirements)
    missing = tuple(check.requirement for check in checks if not check.satisfied)
    blockers = list(template_dry_run.blockers)
    blockers.extend(
        f"missing {requirement.category.value}: {requirement.requirement_id}"
        for requirement in missing
    )
    return ResearchProgramDependencyPreflight(
        experiment=experiment,
        template_dry_run=template_dry_run,
        requirements=requirements,
        checks=checks,
        blockers=tuple(blockers),
        requirements_checksum=sha256_json(requirements),
        inventory_checksum=_inventory_checksum(inventory),
    )


def _required_horizons(
    template: FirstProgramTemplate,
    runtime: FirstProgramRuntime,
) -> tuple[int, ...]:
    grid = template.static_parameter_grid.get("variables.forward_horizon")
    if grid is not None:
        horizons = tuple(
            value for value in grid if isinstance(value, int) and not isinstance(value, bool)
        )
        if len(horizons) != len(grid):
            raise ValueError("forward-horizon search grid must contain only integer session counts")
        return horizons
    value = template.base_variables.get("forward_horizon")
    if isinstance(value, int) and not isinstance(value, bool):
        return (value,)
    resolved = runtime.resolved_values or {}
    primary = resolved.get("frozen_primary_outcome")
    if isinstance(primary, dict):
        horizon = primary.get("horizon")
        if isinstance(horizon, int) and not isinstance(horizon, bool):
            return (horizon,)
    return ()


def _required_comparators(
    experiment: FirstProgramExperiment,
    runtime: FirstProgramRuntime,
    template: FirstProgramTemplate,
) -> tuple[str, ...]:
    if experiment not in {
        FirstProgramExperiment.I_COMBINED_VALIDATION,
        FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
    }:
        return template.comparators
    resolved = runtime.resolved_values or {}
    comparator = resolved.get("frozen_comparator")
    if isinstance(comparator, str) and comparator.strip():
        return (comparator,)
    return template.comparators


def _required_risk_policies(
    experiment: FirstProgramExperiment,
    runtime: FirstProgramRuntime,
) -> tuple[str, ...]:
    if experiment is FirstProgramExperiment.H_STOPS:
        return _H_STOP_POLICIES
    if experiment is not FirstProgramExperiment.I_COMBINED_VALIDATION:
        return ()
    resolved = runtime.resolved_values or {}
    candidates = resolved.get("frozen_risk_policy_candidates")
    if candidates is None:
        return ()
    if not isinstance(candidates, list):
        raise ValueError("frozen_risk_policy_candidates must be a list of policy identifiers")
    policies = tuple(item for item in candidates if isinstance(item, str) and item.strip())
    if len(policies) != len(candidates):
        raise ValueError("frozen_risk_policy_candidates must contain non-empty strings")
    return policies


def _check_requirement(
    requirement: DependencyRequirement,
    inventory: ResearchDependencyInventory,
) -> DependencyCheck:
    category = requirement.category
    identifier = requirement.requirement_id
    if category is DependencyCategory.DATASET:
        satisfied = identifier in inventory.dataset_versions
    elif category is DependencyCategory.UNIVERSE:
        satisfied = identifier in inventory.universe_versions
    elif category is DependencyCategory.FEATURE:
        satisfied = identifier in inventory.feature_definitions
    elif category is DependencyCategory.EVENT:
        satisfied = identifier in inventory.event_definitions
    elif category is DependencyCategory.OUTCOME_HORIZON:
        satisfied = int(identifier) in inventory.outcome_horizons
    elif category is DependencyCategory.RISK_POLICY:
        satisfied = identifier in inventory.risk_policy_ids
    elif category is DependencyCategory.COMPARATOR:
        satisfied = identifier in inventory.comparator_ids
    elif category is DependencyCategory.VALIDATION_PLAN:
        satisfied = identifier in inventory.validation_plan_ids
    elif category is DependencyCategory.ASSUMPTION:
        satisfied = identifier in inventory.assumption_ids
    elif category is DependencyCategory.CAPABILITY:
        satisfied = identifier in inventory.capabilities
    elif category is DependencyCategory.PRIOR_EXPERIMENT:
        satisfied = FirstProgramExperiment(identifier) in inventory.completed_experiments
    else:
        raise AssertionError(f"unhandled dependency category {category}")
    evidence = f"inventory:{category.value}:{identifier}" if satisfied else None
    return DependencyCheck(requirement=requirement, satisfied=satisfied, evidence=evidence)


def _inventory_checksum(inventory: ResearchDependencyInventory) -> str:
    payload = {
        "dataset_versions": sorted(inventory.dataset_versions),
        "universe_versions": sorted(inventory.universe_versions),
        "feature_definitions": sorted(inventory.feature_definitions),
        "event_definitions": sorted(inventory.event_definitions),
        "outcome_horizons": sorted(inventory.outcome_horizons),
        "risk_policy_ids": sorted(inventory.risk_policy_ids),
        "comparator_ids": sorted(inventory.comparator_ids),
        "validation_plan_ids": sorted(inventory.validation_plan_ids),
        "assumption_ids": sorted(inventory.assumption_ids),
        "capabilities": sorted(inventory.capabilities),
        "completed_experiments": sorted(item.value for item in inventory.completed_experiments),
    }
    return sha256_json(payload)


def _requirement(
    category: DependencyCategory,
    requirement_id: str,
    description: str,
) -> DependencyRequirement:
    return DependencyRequirement(
        category=category,
        requirement_id=requirement_id,
        description=description,
    )


def _deduplicate_requirements(
    requirements: tuple[DependencyRequirement, ...],
) -> tuple[DependencyRequirement, ...]:
    seen: set[tuple[DependencyCategory, str]] = set()
    result: list[DependencyRequirement] = []
    for requirement in requirements:
        key = (requirement.category, requirement.requirement_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(requirement)
    return tuple(result)


__all__ = [
    "DEPENDENCY_PLANNER_VERSION",
    "DependencyCategory",
    "DependencyCheck",
    "DependencyRequirement",
    "ResearchDependencyInventory",
    "ResearchProgramDependencyPreflight",
    "first_program_dependency_requirements",
    "preflight_first_program_dependencies",
]
