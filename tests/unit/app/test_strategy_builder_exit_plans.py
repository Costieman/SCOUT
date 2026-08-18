from __future__ import annotations

import pytest

from trade_scout.app.strategy_builder_exit_plans import (
    exit_plan_json_ready,
    exit_plan_token,
    parse_exit_plan_tokens,
)
from trade_scout.risk.exit_policies import (
    ExitFamily,
    ManagedExitPlan,
    SameBarExitPolicy,
    TargetFamily,
)


def test_parse_fixed_percent_stop_and_atr_target_uses_human_units() -> None:
    plans = parse_exit_plan_tokens(
        ["fixed:5|atr:2"],
        same_bar_policy=SameBarExitPolicy.STOP_FIRST,
    )

    assert plans == (
        ManagedExitPlan(
            stop_family=ExitFamily.FIXED_PERCENT_STOP,
            stop_value=0.05,
            target_family=TargetFamily.ATR_MULTIPLE,
            target_value=2.0,
            same_bar_policy=SameBarExitPolicy.STOP_FIRST,
        ),
    )


def test_trailing_percent_and_fixed_target_round_trip_browser_units() -> None:
    plan = ManagedExitPlan(
        stop_family=ExitFamily.TRAILING_PERCENT_STOP,
        stop_value=0.08,
        target_family=TargetFamily.FIXED_PERCENT,
        target_value=0.15,
        same_bar_policy=SameBarExitPolicy.TARGET_FIRST,
    )

    token = exit_plan_token(plan)
    display = exit_plan_json_ready(plan)
    repeated = parse_exit_plan_tokens(
        [token],
        same_bar_policy=SameBarExitPolicy.TARGET_FIRST,
    )

    assert token == "trailing:8|fixed:15"
    assert display["stop_value"] == pytest.approx(8.0)
    assert display["target_value"] == pytest.approx(15.0)
    assert repeated == (plan,)


def test_no_target_token_keeps_horizon_as_fallback_not_a_target() -> None:
    plans = parse_exit_plan_tokens(
        ["atr:2|none:"],
        same_bar_policy=SameBarExitPolicy.STOP_FIRST,
    )

    assert plans[0].stop_family is ExitFamily.ATR_STOP
    assert plans[0].target_family is None
    assert plans[0].target_value is None
    assert exit_plan_token(plans[0]) == "atr:2|none:"


def test_r_target_and_duplicate_plans_are_explicit() -> None:
    source = "trailing_atr:2.5|r:3"
    plans = parse_exit_plan_tokens(
        [source],
        same_bar_policy=SameBarExitPolicy.STOP_FIRST,
    )

    assert plans[0].stop_family is ExitFamily.TRAILING_ATR_STOP
    assert plans[0].target_family is TargetFamily.R_MULTIPLE
    assert plans[0].target_value == pytest.approx(3.0)

    with pytest.raises(ValueError, match="duplicates"):
        parse_exit_plan_tokens(
            [source, source],
            same_bar_policy=SameBarExitPolicy.STOP_FIRST,
        )


def test_invalid_tokens_fail_before_research() -> None:
    with pytest.raises(ValueError, match="stop:value"):
        parse_exit_plan_tokens(["fixed:5"], same_bar_policy=SameBarExitPolicy.STOP_FIRST)
    with pytest.raises(ValueError, match="unsupported profit target"):
        parse_exit_plan_tokens(
            ["fixed:5|mystery:2"],
            same_bar_policy=SameBarExitPolicy.STOP_FIRST,
        )
