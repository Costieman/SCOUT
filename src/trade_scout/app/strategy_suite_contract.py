"""Cross-layer stability contract for executable Strategy Suites.

A launch plan may be labelled READY only when the exact parameters it places into the Strategy
Builder satisfy the same backend and browser-facing constraints used by an operator-built run.
This module is validation only; it never changes a suite, a research result, or a saved experiment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.strategy_indicator_catalog import available_indicator_metrics
from trade_scout.app.strategy_suite_workflow import (
    SuiteLaunchPlan,
    SuiteLaunchStatus,
    built_in_suite_launch_plans,
)
from trade_scout.app.visual_rule_builder import recover_visual_conditions
from trade_scout.features.parameterized_expression import parse_parameterized_feature_name
from trade_scout.features.parameterized_indicators import IndicatorMetric
from trade_scout.patterns.consolidation_breakout import TrendFilter
from trade_scout.statistics.strategy_research import available_strategy_features


@dataclass(frozen=True, slots=True)
class SuiteContractIssue:
    """One actionable reason an executable suite is unsafe to expose as READY."""

    suite_id: str
    field: str
    issue_code: str
    message: str


@dataclass(frozen=True, slots=True)
class ThresholdContract:
    """Browser-compatible numeric threshold bounds for one feature."""

    minimum: float
    maximum: float
    step: float


def validate_suite_launch_plan(plan: SuiteLaunchPlan) -> tuple[SuiteContractIssue, ...]:
    """Return blocking contract issues for one READY launch plan."""

    if plan.launch_status is not SuiteLaunchStatus.READY:
        return ()
    p = plan.builder_parameters
    issues: list[SuiteContractIssue] = []

    def issue(field: str, code: str, message: str) -> None:
        issues.append(SuiteContractIssue(plan.suite_id, field, code, message))

    if p.get("universe") != "reviewed_canonical":
        issue("universe", "unsupported_universe", "READY suites must use reviewed_canonical.")

    try:
        family = EntryFamily(str(p.get("entry_family", "")))
    except ValueError:
        issue("entry_family", "unsupported_entry_family", "Entry family is not executable.")
        return tuple(issues)

    _validate_integer_choice(plan, "lookback_years", {1, 2, 3, 5, 10, 20}, issues)
    _validate_integer_choice(plan, "horizon", {2, 3, 5, 10, 20, 40, 60, 120, 252}, issues)

    if family is EntryFamily.FEATURE_EXPRESSION:
        expression = str(p.get("expression", "")).strip()
        if not expression:
            issue("expression", "missing_expression", "Feature-expression suite has no expression.")
        else:
            conditions = recover_visual_conditions(expression)
            if not conditions:
                issue(
                    "expression",
                    "unrecoverable_expression",
                    "Suite expression cannot be represented by the current visual Builder.",
                )
            for index, condition in enumerate(conditions, start=1):
                contract = threshold_contract(condition.feature_name)
                if contract is None:
                    issue(
                        f"entry_condition_{index}",
                        "missing_threshold_contract",
                        f"No Builder threshold contract exists for {condition.feature_name!r}.",
                    )
                elif not value_matches_threshold_contract(condition.value, contract):
                    issue(
                        f"entry_condition_{index}",
                        "invalid_threshold",
                        (
                            f"{condition.feature_name} value {condition.value:g} is outside or off-step; "
                            f"expected {contract.minimum:g}..{contract.maximum:g} step {contract.step:g}."
                        ),
                    )
        rank_feature = str(p.get("rank_feature", ""))
        if not _supported_feature(rank_feature):
            issue(
                "rank_feature",
                "unsupported_rank_feature",
                f"Unknown rank feature {rank_feature!r}.",
            )
        if p.get("rank_direction") not in {"asc", "desc"}:
            issue("rank_direction", "invalid_rank_direction", "Rank direction must be asc or desc.")
        _validate_integer_range(plan, "per_session_limit", 1, 500, issues)
    elif family is EntryFamily.CONSOLIDATION_BREAKOUT:
        _validate_integer_range(plan, "duration", 5, 252, issues)
        _validate_float_range(plan, "max_range_pct", 0.0, 100.0, issues, lower_open=True)
        try:
            TrendFilter(str(p.get("trend_filter", "")))
        except ValueError:
            issue("trend_filter", "invalid_trend_filter", "Trend filter is not supported.")
        volume_ratio = str(p.get("volume_ratio", "none"))
        if volume_ratio != "none":
            try:
                if float(volume_ratio) <= 0:
                    raise ValueError
            except ValueError:
                issue(
                    "volume_ratio", "invalid_volume_ratio", "Volume ratio must be none or positive."
                )

    return tuple(issues)


def validate_all_ready_suites() -> tuple[SuiteContractIssue, ...]:
    """Validate every built-in launch plan currently exposed as executable."""

    return tuple(
        issue
        for plan in built_in_suite_launch_plans()
        for issue in validate_suite_launch_plan(plan)
    )


def threshold_contract(feature_name: str) -> ThresholdContract | None:
    """Resolve the numeric contract used by the visual Builder for a feature threshold."""

    static = {item.feature_name: item for item in available_indicator_metrics()}.get(feature_name)
    if static is not None:
        return ThresholdContract(static.min_value, static.max_value, static.step)
    try:
        spec = parse_parameterized_feature_name(feature_name)
    except ValueError:
        return None

    metric = spec.metric
    binary = {
        IndicatorMetric.MA_CROSS_UP,
        IndicatorMetric.MA_CROSS_DOWN,
        IndicatorMetric.BB_UPPER_REACHED,
        IndicatorMetric.BB_LOWER_REACHED,
        IndicatorMetric.BB_UPPER_CROSS_UP,
        IndicatorMetric.BB_LOWER_CROSS_DOWN,
        IndicatorMetric.BB_MIDDLE_CROSS_UP,
        IndicatorMetric.BB_MIDDLE_CROSS_DOWN,
        IndicatorMetric.MACD_CROSS_UP,
        IndicatorMetric.MACD_CROSS_DOWN,
        IndicatorMetric.PRIOR_HIGH_BREAKOUT,
    }
    if metric in binary:
        return ThresholdContract(0.0, 1.0, 1.0)
    family = spec.family.value
    if family == "rsi":
        return ThresholdContract(0.0, 100.0, 0.1)
    if family == "relative_volume":
        return ThresholdContract(0.0, 20.0, 0.05)
    if family == "average_dollar_volume":
        return ThresholdContract(0.0, 100_000_000_000.0, 1_000_000.0)
    if family == "historical_volatility":
        return ThresholdContract(0.0, 500.0, 0.5)
    if family == "atr":
        return ThresholdContract(0.0, 100.0, 0.1)
    if metric is IndicatorMetric.BB_POSITION:
        return ThresholdContract(-2.0, 3.0, 0.01)
    return ThresholdContract(-100.0, 500.0, 0.1)


def value_matches_threshold_contract(value: float, contract: ThresholdContract) -> bool:
    """Match HTML number-input min/max/step semantics with floating-point tolerance."""

    if not math.isfinite(value) or value < contract.minimum or value > contract.maximum:
        return False
    steps = (value - contract.minimum) / contract.step
    return math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-8)


def _supported_feature(feature_name: str) -> bool:
    if feature_name in available_strategy_features():
        return True
    try:
        parse_parameterized_feature_name(feature_name)
    except ValueError:
        return False
    return True


def _validate_integer_choice(
    plan: SuiteLaunchPlan,
    field: str,
    allowed: set[int],
    issues: list[SuiteContractIssue],
) -> None:
    try:
        value = int(str(plan.builder_parameters.get(field, "")))
    except ValueError:
        value = -1
    if value not in allowed:
        issues.append(
            SuiteContractIssue(
                plan.suite_id, field, "invalid_choice", f"{field} must be one of {sorted(allowed)}."
            )
        )


def _validate_integer_range(
    plan: SuiteLaunchPlan,
    field: str,
    minimum: int,
    maximum: int,
    issues: list[SuiteContractIssue],
) -> None:
    raw = str(plan.builder_parameters.get(field, ""))
    try:
        value = int(raw)
        exact = str(value) == raw
    except ValueError:
        value, exact = minimum - 1, False
    if not exact or not minimum <= value <= maximum:
        issues.append(
            SuiteContractIssue(
                plan.suite_id,
                field,
                "invalid_integer_range",
                f"{field} must be a whole number from {minimum} to {maximum}.",
            )
        )


def _validate_float_range(
    plan: SuiteLaunchPlan,
    field: str,
    minimum: float,
    maximum: float,
    issues: list[SuiteContractIssue],
    *,
    lower_open: bool = False,
) -> None:
    try:
        value = float(str(plan.builder_parameters.get(field, "")))
    except ValueError:
        value = math.nan
    lower_ok = value > minimum if lower_open else value >= minimum
    if not math.isfinite(value) or not lower_ok or value > maximum:
        issues.append(
            SuiteContractIssue(
                plan.suite_id,
                field,
                "invalid_numeric_range",
                f"{field} must be within the Builder's supported range.",
            )
        )


__all__ = [
    "SuiteContractIssue",
    "ThresholdContract",
    "threshold_contract",
    "validate_all_ready_suites",
    "validate_suite_launch_plan",
    "value_matches_threshold_contract",
]
