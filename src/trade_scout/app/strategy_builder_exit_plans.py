"""Parse and serialize managed Strategy Builder stop-plus-target plans.

Browser values use human-facing percentages while the analytical risk engine uses decimal returns.
This module is an application adapter only; trigger and fill logic remains in ``risk.exit_policies``.
"""

from __future__ import annotations

from trade_scout.risk.exit_policies import (
    ExitFamily,
    ManagedExitPlan,
    SameBarExitPolicy,
    TargetFamily,
)

_STOP_FAMILIES = {
    "fixed": ExitFamily.FIXED_PERCENT_STOP,
    "trailing": ExitFamily.TRAILING_PERCENT_STOP,
    "atr": ExitFamily.ATR_STOP,
    "trailing_atr": ExitFamily.TRAILING_ATR_STOP,
}
_TARGET_FAMILIES = {
    "fixed": TargetFamily.FIXED_PERCENT,
    "atr": TargetFamily.ATR_MULTIPLE,
    "r": TargetFamily.R_MULTIPLE,
}
_REVERSE_STOP = {value: key for key, value in _STOP_FAMILIES.items()}
_REVERSE_TARGET = {value: key for key, value in _TARGET_FAMILIES.items()}


def parse_exit_plan_tokens(
    values: list[str],
    *,
    same_bar_policy: SameBarExitPolicy,
) -> tuple[ManagedExitPlan, ...]:
    """Parse repeated ``stop:value|target:value`` browser tokens into typed plans."""

    plans = tuple(
        _parse_exit_plan_token(value, same_bar_policy=same_bar_policy) for value in values
    )
    if len(set(plans)) != len(plans):
        raise ValueError("managed exit plans must not contain duplicates")
    return plans


def exit_plan_token(plan: ManagedExitPlan) -> str:
    """Serialize one typed plan into the stable human-unit browser token."""

    stop_key = _REVERSE_STOP[plan.stop_family]
    stop_value = _display_stop_value(plan)
    if plan.target_family is None:
        target = "none:"
    else:
        target_key = _REVERSE_TARGET[plan.target_family]
        target_value = _display_target_value(plan)
        target = f"{target_key}:{target_value:g}"
    return f"{stop_key}:{stop_value:g}|{target}"


def exit_plan_json_ready(plan: ManagedExitPlan) -> dict[str, object]:
    """Return one browser-ready plan using display units rather than analytical decimals."""

    return {
        "stop_family": _REVERSE_STOP[plan.stop_family],
        "stop_value": _display_stop_value(plan),
        "target_family": "none"
        if plan.target_family is None
        else _REVERSE_TARGET[plan.target_family],
        "target_value": None if plan.target_family is None else _display_target_value(plan),
    }


def _parse_exit_plan_token(value: str, *, same_bar_policy: SameBarExitPolicy) -> ManagedExitPlan:
    source = value.strip()
    if not source or "|" not in source:
        raise ValueError("exit_plan must use stop:value|target:value format")
    stop_source, target_source = source.split("|", 1)
    stop_family_key, stop_value = _component(stop_source, "protective stop")
    stop_family = _STOP_FAMILIES.get(stop_family_key)
    if stop_family is None:
        raise ValueError(f"unsupported protective stop family {stop_family_key!r}")
    resolved_stop = stop_value / 100.0 if "percent" in stop_family.value else stop_value

    target_family_key, target_value = _optional_component(target_source)
    if target_family_key == "none":
        target_family = None
        resolved_target = None
    else:
        target_family = _TARGET_FAMILIES.get(target_family_key)
        if target_family is None:
            raise ValueError(f"unsupported profit target family {target_family_key!r}")
        if target_value is None:
            raise ValueError("profit target value is required")
        resolved_target = target_value / 100.0 if target_family is TargetFamily.FIXED_PERCENT else target_value
    return ManagedExitPlan(
        stop_family=stop_family,
        stop_value=resolved_stop,
        target_family=target_family,
        target_value=resolved_target,
        same_bar_policy=same_bar_policy,
    )


def _component(source: str, label: str) -> tuple[str, float]:
    family, separator, raw_value = source.partition(":")
    if not separator or not family.strip() or not raw_value.strip():
        raise ValueError(f"{label} requires family:value")
    value = float(raw_value)
    if not value > 0:
        raise ValueError(f"{label} value must be positive")
    return family.strip(), value


def _optional_component(source: str) -> tuple[str, float | None]:
    family, separator, raw_value = source.partition(":")
    if not separator or not family.strip():
        raise ValueError("profit target requires family:value or none:")
    family = family.strip()
    if family == "none":
        if raw_value.strip():
            raise ValueError("none profit target must not include a value")
        return family, None
    if not raw_value.strip():
        raise ValueError("profit target value is required")
    value = float(raw_value)
    if not value > 0:
        raise ValueError("profit target value must be positive")
    return family, value


def _display_stop_value(plan: ManagedExitPlan) -> float:
    if plan.stop_family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP}:
        return plan.stop_value * 100.0
    return plan.stop_value


def _display_target_value(plan: ManagedExitPlan) -> float:
    if plan.target_value is None or plan.target_family is None:
        raise ValueError("profit target display requires a configured target")
    if plan.target_family is TargetFamily.FIXED_PERCENT:
        return plan.target_value * 100.0
    return plan.target_value


__all__ = [
    "exit_plan_json_ready",
    "exit_plan_token",
    "parse_exit_plan_tokens",
]
