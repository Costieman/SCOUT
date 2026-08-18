"""Bridge strategy-suite research templates into reproducible Strategy Builder sessions.

Phase 5 resolves catalog suites into explicit builder launch configurations without pretending that
unsupported structural logic is executable. Phase 6 adds deterministic fingerprints and one-axis
iteration proposals so Research Brains can distinguish an exact rerun from a controlled neighboring
experiment.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from trade_scout.app.strategy_suite_registry import (
    StrategySuite,
    SuiteImplementationStatus,
    built_in_strategy_suites,
    strategy_suite,
)


class SuiteLaunchStatus(StrEnum):
    """Whether one suite has a truthful executable bridge into the current Strategy Builder."""

    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SuiteLaunchPlan:
    """Machine-resolved starting configuration for one suite."""

    suite_id: str
    suite_version: str
    launch_status: SuiteLaunchStatus
    builder_parameters: Mapping[str, str]
    unresolved_capabilities: tuple[str, ...] = ()
    note: str = ""
    version: str = "suite-launch-v0.1"

    def __post_init__(self) -> None:
        if not self.suite_id.strip() or not self.suite_version.strip() or not self.version.strip():
            raise ValueError("suite launch identity/version must be non-empty")
        if self.launch_status is SuiteLaunchStatus.READY and self.unresolved_capabilities:
            raise ValueError("READY suite launch plans cannot carry unresolved capabilities")
        if self.launch_status is not SuiteLaunchStatus.READY and not self.note.strip():
            raise ValueError("non-ready suite launch plans must explain the limitation")

    @property
    def executable(self) -> bool:
        return self.launch_status is SuiteLaunchStatus.READY

    def query_parameters(self, *, brain_id: str | None = None) -> Mapping[str, str]:
        values = dict(self.builder_parameters)
        values["suite"] = self.suite_id
        if brain_id:
            values["brain"] = brain_id.strip()
        return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class ResearchConfiguration:
    """Canonical parameter state used for duplicate detection and controlled iteration."""

    suite_id: str
    parameters: Mapping[str, str]
    version: str = "research-configuration-v0.1"

    def __post_init__(self) -> None:
        if not self.suite_id.strip() or not self.version.strip():
            raise ValueError("research configuration identity/version must be non-empty")
        if not self.parameters:
            raise ValueError("research configuration must contain at least one parameter")

    @property
    def fingerprint(self) -> str:
        payload = {
            "suite_id": self.suite_id,
            "version": self.version,
            "parameters": sorted((str(key), str(value)) for key, value in self.parameters.items()),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class IterationProposal:
    """A controlled neighboring configuration changing exactly one declared suite axis."""

    axis: str
    prior_value: str
    proposed_value: str
    rationale: str
    configuration: ResearchConfiguration


def strategy_suite_launch_plan(suite_id: str) -> SuiteLaunchPlan:
    """Resolve one catalog suite to the current truthful Strategy Builder bridge."""

    suite = strategy_suite(suite_id)
    parameters = _EXECUTABLE_PARAMETERS.get(suite.suite_id)
    if parameters is not None:
        return SuiteLaunchPlan(
            suite_id=suite.suite_id,
            suite_version=suite.version,
            launch_status=SuiteLaunchStatus.READY,
            builder_parameters=MappingProxyType(dict(parameters)),
            note="Resolved to existing point-in-time Strategy Builder semantics.",
        )

    unresolved = _unresolved_capabilities(suite)
    status = (
        SuiteLaunchStatus.BLOCKED
        if suite.implementation_status is SuiteImplementationStatus.REQUIRES_PATTERN
        else SuiteLaunchStatus.PARTIAL
    )
    return SuiteLaunchPlan(
        suite_id=suite.suite_id,
        suite_version=suite.version,
        launch_status=status,
        builder_parameters=MappingProxyType({"universe": "reviewed_canonical"}),
        unresolved_capabilities=unresolved,
        note=_limitation_note(suite, unresolved),
    )


def built_in_suite_launch_plans() -> tuple[SuiteLaunchPlan, ...]:
    """Return launch status for the complete twenty-suite catalog in stable order."""

    return tuple(strategy_suite_launch_plan(item.suite_id) for item in built_in_strategy_suites())


def configuration_from_launch_plan(
    plan: SuiteLaunchPlan,
    *,
    overrides: Mapping[str, str] | None = None,
) -> ResearchConfiguration:
    """Create one canonical research configuration from a launch plan and explicit overrides."""

    if not plan.executable:
        raise ValueError(f"suite {plan.suite_id} does not yet have a complete executable bridge")
    parameters = dict(plan.builder_parameters)
    if overrides:
        parameters.update((str(key), str(value)) for key, value in overrides.items())
    return ResearchConfiguration(suite_id=plan.suite_id, parameters=MappingProxyType(parameters))


def is_exact_rerun(
    candidate: ResearchConfiguration,
    prior: ResearchConfiguration | str,
) -> bool:
    """Return whether candidate exactly matches a prior canonical configuration."""

    prior_fingerprint = prior if isinstance(prior, str) else prior.fingerprint
    return candidate.fingerprint == prior_fingerprint


def propose_single_axis_iteration(
    current: ResearchConfiguration,
    *,
    axis: str,
    proposed_value: str,
) -> IterationProposal:
    """Change exactly one declared suite axis while preserving every other parameter."""

    suite = strategy_suite(current.suite_id)
    normalized_axis = axis.strip()
    if normalized_axis not in suite.parameter_axes:
        choices = suite.parameter_axes
        raise ValueError(
            f"axis {axis!r} is not declared by {suite.suite_id}; choose one of {choices}"
        )
    parameter_name = _AXIS_PARAMETER_NAMES.get((suite.suite_id, normalized_axis), normalized_axis)
    if parameter_name not in current.parameters:
        raise ValueError(
            f"declared axis {normalized_axis!r} is not yet machine-resolved for {suite.suite_id}"
        )
    prior_value = str(current.parameters[parameter_name])
    next_value = str(proposed_value).strip()
    if not next_value or next_value == prior_value:
        raise ValueError("iteration must change the selected axis to a different non-empty value")
    changed = dict(current.parameters)
    changed[parameter_name] = next_value
    candidate = replace(current, parameters=MappingProxyType(changed))
    differing = [
        key
        for key in set(current.parameters).union(candidate.parameters)
        if current.parameters.get(key) != candidate.parameters.get(key)
    ]
    if differing != [parameter_name]:
        raise RuntimeError("controlled iteration changed more than one machine parameter")
    rationale = (
        f"Change only {normalized_axis} from {prior_value} to {next_value}; preserve the "
        "remaining configuration so any result difference has a clear local interpretation."
    )
    return IterationProposal(
        axis=normalized_axis,
        prior_value=prior_value,
        proposed_value=next_value,
        rationale=rationale,
        configuration=candidate,
    )


_EXECUTABLE_PARAMETERS: dict[str, dict[str, str]] = {
    "TS-S01-CONSOLIDATION-BREAKOUT": {
        "universe": "reviewed_canonical",
        "entry_family": "consolidation_breakout",
        "lookback_years": "2",
        "horizon": "20",
        "duration": "30",
        "max_range_pct": "12",
        "trend_filter": "above_rising_sma_200",
        "volume_ratio": "none",
    },
    "TS-S02-DONCHIAN-BREAKOUT": {
        "universe": "reviewed_canonical",
        "entry_family": "feature_expression",
        "lookback_years": "2",
        "horizon": "20",
        "expression": "distance_prior_high_20_pct > 0",
        "rank_feature": "distance_prior_high_20_pct",
        "rank_direction": "desc",
        "per_session_limit": "25",
    },
    "TS-S14-TIME-SERIES-MOMENTUM": {
        "universe": "reviewed_canonical",
        "entry_family": "feature_expression",
        "lookback_years": "2",
        "horizon": "20",
        "expression": "return_252 > 0",
        "rank_feature": "return_252",
        "rank_direction": "desc",
        "per_session_limit": "25",
    },
    "TS-S15-MA-CROSSOVER": {
        "universe": "reviewed_canonical",
        "entry_family": "feature_expression",
        "lookback_years": "2",
        "horizon": "20",
        "expression": "sma_50_200_cross_up == 1",
        "rank_feature": "sma_50_200_spread_pct",
        "rank_direction": "desc",
        "per_session_limit": "25",
    },
    "TS-S16-MACD-TREND": {
        "universe": "reviewed_canonical",
        "entry_family": "feature_expression",
        "lookback_years": "2",
        "horizon": "20",
        "expression": "macd_bullish_cross == 1 and distance_sma_200_pct > 0",
        "rank_feature": "return_20",
        "rank_direction": "desc",
        "per_session_limit": "25",
    },
    "TS-S17-RSI2-MEAN-REVERSION": {
        "universe": "reviewed_canonical",
        "entry_family": "feature_expression",
        "lookback_years": "2",
        "horizon": "10",
        "expression": "pi__rsi__rsi_value__close__p2__wilder < 5 and distance_sma_200_pct > 0",
        "rank_feature": "rsi_wilder_14",
        "rank_direction": "asc",
        "per_session_limit": "25",
    },
    "TS-S18-BB-RSI-MEAN-REVERSION": {
        "universe": "reviewed_canonical",
        "entry_family": "feature_expression",
        "lookback_years": "2",
        "horizon": "10",
        "expression": (
            "pi__bollinger_bands__bb_lower_reached__close__p20__k2 == 1 and rsi_wilder_14 <= 30"
        ),
        "rank_feature": "rsi_wilder_14",
        "rank_direction": "asc",
        "per_session_limit": "25",
    },
}

_AXIS_PARAMETER_NAMES: dict[tuple[str, str], str] = {
    ("TS-S01-CONSOLIDATION-BREAKOUT", "base_duration"): "duration",
    ("TS-S01-CONSOLIDATION-BREAKOUT", "tightness"): "max_range_pct",
    ("TS-S01-CONSOLIDATION-BREAKOUT", "trend_filter"): "trend_filter",
    ("TS-S01-CONSOLIDATION-BREAKOUT", "relative_volume"): "volume_ratio",
    ("TS-S02-DONCHIAN-BREAKOUT", "channel_period"): "expression",
    ("TS-S14-TIME-SERIES-MOMENTUM", "lookback"): "expression",
    ("TS-S15-MA-CROSSOVER", "fast_period"): "expression",
    ("TS-S16-MACD-TREND", "trend_period"): "expression",
    ("TS-S17-RSI2-MEAN-REVERSION", "oversold_threshold"): "expression",
    ("TS-S18-BB-RSI-MEAN-REVERSION", "oversold_threshold"): "expression",
}


def _unresolved_capabilities(suite: StrategySuite) -> tuple[str, ...]:
    resolved = {
        "sma",
        "sma_slope",
        "consolidation_state",
        "close_breakout",
        "relative_volume",
        "prior_high",
        "prior_high_breakout",
        "price_roc",
        "moving_average",
        "ma_cross_up",
        "macd",
        "rsi",
        "bollinger_bands",
        "historical_volatility",
    }
    return tuple(item for item in suite.required_capabilities if item not in resolved)


def _limitation_note(suite: StrategySuite, unresolved: tuple[str, ...]) -> str:
    if suite.implementation_status is SuiteImplementationStatus.REQUIRES_PATTERN:
        return (
            "Catalog template is preserved, but execution is blocked until its structural pattern "
            "detector exists; SCOUT will not substitute a looser indicator approximation."
        )
    if unresolved:
        return "Current builder bridge is incomplete for: " + ", ".join(unresolved) + "."
    return (
        "The catalog recipe still contains state, ranking, exit, or trigger semantics that are not "
        "fully machine-resolved; execution remains partial rather than silently approximated."
    )


__all__ = [
    "IterationProposal",
    "ResearchConfiguration",
    "SuiteLaunchPlan",
    "SuiteLaunchStatus",
    "built_in_suite_launch_plans",
    "configuration_from_launch_plan",
    "is_exact_rerun",
    "propose_single_axis_iteration",
    "strategy_suite_launch_plan",
]
