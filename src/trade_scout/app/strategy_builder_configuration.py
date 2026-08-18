"""Reconstruct executable Strategy Builder requests from immutable resolved experiment config.

This adapter exists so governed follow-up workflows reuse the exact saved Strategy Builder
configuration rather than reverse-engineering browser query strings or inventing a parallel
strategy definition.
"""

from __future__ import annotations

from dataclasses import replace

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.strategy_builder_entry_sweep import EntrySweepParameter
from trade_scout.app.strategy_builder_service import StrategyBuilderRequest
from trade_scout.experiments.contracts import JSONValue
from trade_scout.features.parameterized_expression import parse_parameterized_feature_name
from trade_scout.patterns.consolidation_breakout import TrendFilter
from trade_scout.risk.exit_policies import (
    ExitFamily,
    ManagedExitPlan,
    SameBarExitPolicy,
    TargetFamily,
)


def strategy_request_from_resolved_configuration(
    configuration: dict[str, JSONValue],
) -> StrategyBuilderRequest:
    """Rebuild the frozen executable request represented by one Strategy Builder manifest."""

    if configuration.get("surface") != "visual_strategy_builder":
        raise ValueError("experiment is not a Visual Strategy Builder configuration")
    universe = _mapping(configuration, "universe")
    outcome = _mapping(configuration, "outcome")
    entry = _mapping(configuration, "entry")
    selection = _mapping(configuration, "selection")
    exits = _mapping(configuration, "exit_candidates")
    costs = _mapping(configuration, "execution_costs_bps")
    expression = _string(entry, "expression", default="")
    family = EntryFamily(_string(entry, "family"))
    same_bar_policy = SameBarExitPolicy(
        _string(
            exits,
            "same_bar_stop_target_policy",
            default=SameBarExitPolicy.STOP_FIRST.value,
        )
    )
    managed_plans = _managed_exit_plans(exits.get("managed_exit_plans"), same_bar_policy)
    return StrategyBuilderRequest(
        universe_id=_string(universe, "universe_id", default="reviewed_canonical"),
        lookback_years=_integer(configuration, "historical_lookback_years", default=2),
        horizon=_integer(outcome, "maximum_holding_period_sessions", default=20),
        entry_family=family,
        preset_id=None,
        visual_conditions=(),
        expression=expression,
        rank_feature=_string(selection, "rank_feature", default="return_20"),
        descending=_string(selection, "rank_direction", default="descending") == "descending",
        per_session_limit=_integer(selection, "per_session_limit", default=500),
        duration=_integer(entry, "consolidation_duration_sessions", default=20),
        max_range_pct=_number(entry, "consolidation_max_range_percent", default=12.0) / 100.0,
        trend_filter=TrendFilter(
            _string(entry, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
        ),
        min_breakout_volume_ratio=_optional_number(entry.get("minimum_breakout_volume_ratio")),
        fixed_percentages=(
            ()
            if managed_plans
            else _percentage_tuple(exits.get("fixed_stop_percentages"))
        ),
        trailing_percentages=(
            ()
            if managed_plans
            else _percentage_tuple(exits.get("trailing_stop_percentages"))
        ),
        atr_multiples=() if managed_plans else _number_tuple(exits.get("atr_stop_multiples")),
        trailing_atr_multiples=(
            ()
            if managed_plans
            else _number_tuple(exits.get("trailing_atr_multiples"))
        ),
        managed_exit_plans=managed_plans,
        same_bar_policy=same_bar_policy,
        entry_slippage_bps=_number(costs, "entry_slippage", default=0.0),
        exit_slippage_bps=_number(costs, "normal_exit_slippage", default=0.0),
        stop_slippage_bps=_number(costs, "additional_stop_slippage", default=0.0),
        commission_bps_per_side=_number(costs, "commission_per_side", default=0.0),
    )


def freeze_entry_sweep_candidate(
    configuration: dict[str, JSONValue],
    request: StrategyBuilderRequest,
    candidate_value: float,
) -> StrategyBuilderRequest:
    """Freeze one operator-selected value from an already-declared entry-parameter sweep."""

    variable = configuration.get("research_variable")
    if not isinstance(variable, dict) or variable.get("kind") != "entry_parameter_sweep":
        raise ValueError("source experiment is not an entry-parameter sweep")
    target = _string(variable, "target_feature_name")
    parameter = EntrySweepParameter(_string(variable, "parameter"))
    declared = _number_tuple(variable.get("declared_values"))
    if not declared:
        raise ValueError("entry sweep has no declared values")
    if candidate_value not in declared:
        raise ValueError(
            f"candidate value {candidate_value:g} was not part of the source declared sweep"
        )
    spec = parse_parameterized_feature_name(target)
    if parameter is EntrySweepParameter.STANDARD_DEVIATIONS:
        resolved = replace(spec, standard_deviations=candidate_value)
    else:
        integer = int(candidate_value)
        if float(integer) != candidate_value:
            raise ValueError(f"{parameter.value} candidate must be a whole trading-day value")
        if parameter is EntrySweepParameter.PERIOD:
            resolved = replace(spec, period=integer)
        elif parameter is EntrySweepParameter.FAST_PERIOD:
            resolved = replace(spec, fast_period=integer)
        elif parameter is EntrySweepParameter.SLOW_PERIOD:
            resolved = replace(spec, slow_period=integer)
        elif parameter is EntrySweepParameter.SIGNAL_PERIOD:
            resolved = replace(spec, signal_period=integer)
        else:
            raise ValueError(f"unsupported entry sweep parameter {parameter.value!r}")
    if target not in request.expression:
        raise ValueError("entry sweep target is absent from the frozen source expression")
    return replace(
        request,
        expression=request.expression.replace(target, resolved.feature_name),
        preset_id=None,
        visual_conditions=(),
    )


def source_declared_entry_sweep_values(
    configuration: dict[str, JSONValue],
) -> tuple[float, ...]:
    """Return declared source-sweep values for operator choice, or an empty tuple."""

    variable = configuration.get("research_variable")
    if not isinstance(variable, dict) or variable.get("kind") != "entry_parameter_sweep":
        return ()
    return _number_tuple(variable.get("declared_values"))


def _managed_exit_plans(
    value: JSONValue | None,
    same_bar_policy: SameBarExitPolicy,
) -> tuple[ManagedExitPlan, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("resolved managed exit plans must be a list")
    plans: list[ManagedExitPlan] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("resolved managed exit plan must be a mapping")
        stop_family = ExitFamily(_string(item, "stop_family"))
        stop_value = _number(item, "stop_value", default=0.0)
        raw_target_family = item.get("target_family")
        if raw_target_family is None:
            target_family = None
            target_value = None
        else:
            if not isinstance(raw_target_family, str):
                raise ValueError("resolved target_family must be text or null")
            target_family = TargetFamily(raw_target_family)
            target_value = _number(item, "target_value", default=0.0)
        plans.append(
            ManagedExitPlan(
                stop_family=stop_family,
                stop_value=stop_value,
                target_family=target_family,
                target_value=target_value,
                same_bar_policy=same_bar_policy,
            )
        )
    return tuple(plans)


def _mapping(configuration: dict[str, JSONValue], key: str) -> dict[str, JSONValue]:
    value = configuration.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"resolved Strategy Builder configuration is missing {key!r}")
    return value


def _string(
    mapping: dict[str, JSONValue],
    key: str,
    *,
    default: str | None = None,
) -> str:
    value = mapping.get(key)
    if value is None and default is not None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"resolved configuration field {key!r} must be text")
    return value


def _integer(
    mapping: dict[str, JSONValue],
    key: str,
    *,
    default: int,
) -> int:
    value = mapping.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"resolved configuration field {key!r} must be an integer")
    return value


def _number(
    mapping: dict[str, JSONValue],
    key: str,
    *,
    default: float,
) -> float:
    value = mapping.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"resolved configuration field {key!r} must be numeric")
    return float(value)


def _optional_number(value: JSONValue | None) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError("resolved optional numeric field has invalid type")
    return float(value)


def _number_tuple(value: JSONValue | None) -> tuple[float, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("resolved numeric grid must be a list")
    result: list[float] = []
    for item in value:
        if not isinstance(item, int | float) or isinstance(item, bool):
            raise ValueError("resolved numeric grid contains a non-numeric value")
        result.append(float(item))
    return tuple(result)


def _percentage_tuple(value: JSONValue | None) -> tuple[float, ...]:
    return tuple(item / 100.0 for item in _number_tuple(value))


__all__ = [
    "freeze_entry_sweep_candidate",
    "source_declared_entry_sweep_values",
    "strategy_request_from_resolved_configuration",
]
