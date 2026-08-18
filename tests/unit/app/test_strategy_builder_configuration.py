from __future__ import annotations

import pytest

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.strategy_builder_configuration import (
    freeze_entry_sweep_candidate,
    source_declared_entry_sweep_values,
    strategy_request_from_resolved_configuration,
)
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
)
from trade_scout.risk.exit_policies import (
    ExitFamily,
    SameBarExitPolicy,
    TargetFamily,
)


def _configuration(*, sweep: bool = False, managed: bool = False) -> dict[str, object]:
    ma = ParameterizedIndicatorSpec(
        family=IndicatorFamily.MOVING_AVERAGE,
        metric=IndicatorMetric.MA_DISTANCE_PCT,
        period=20,
    )
    exit_candidates: dict[str, object] = {
        "hold_to_horizon_control": True,
        "fixed_stop_percentages": [5.0],
        "trailing_stop_percentages": [],
        "atr_stop_multiples": [2.0],
        "trailing_atr_multiples": [],
    }
    if managed:
        exit_candidates.update(
            {
                "same_bar_stop_target_policy": "target_first",
                "managed_exit_plans": [
                    {
                        "stop_family": "trailing_percent_stop",
                        "stop_value": 0.08,
                        "target_family": "atr_multiple_target",
                        "target_value": 2.0,
                        "same_bar_policy": "target_first",
                    }
                ],
                "legacy_stop_grid_used": False,
            }
        )
    configuration: dict[str, object] = {
        "surface": "visual_strategy_builder",
        "research_state": "EXPLORATORY",
        "provider_calls_made": False,
        "universe": {
            "universe_id": "reviewed_canonical",
            "point_in_time_membership_claimed": False,
        },
        "historical_lookback_years": 2,
        "outcome": {
            "maximum_holding_period_sessions": 20,
            "forced_exit_at_maximum_holding_period": True,
        },
        "entry": {
            "family": "feature_expression",
            "expression": f"{ma.feature_name} > 0",
            "consolidation_duration_sessions": 20,
            "consolidation_max_range_percent": 12.0,
            "trend_filter": "above_sma_50_100_200",
            "minimum_breakout_volume_ratio": None,
        },
        "selection": {
            "rank_feature": "return_20",
            "rank_direction": "descending",
            "per_session_limit": 500,
        },
        "exit_candidates": exit_candidates,
        "execution_costs_bps": {
            "entry_slippage": 5.0,
            "normal_exit_slippage": 5.0,
            "additional_stop_slippage": 10.0,
            "commission_per_side": 0.0,
        },
    }
    if sweep:
        configuration["research_variable"] = {
            "kind": "entry_parameter_sweep",
            "target_feature_name": ma.feature_name,
            "parameter": "period",
            "declared_values": [10.0, 20.0, 30.0],
        }
    return configuration


def test_reconstructs_frozen_strategy_builder_request() -> None:
    request = strategy_request_from_resolved_configuration(_configuration())  # type: ignore[arg-type]

    assert request.entry_family is EntryFamily.FEATURE_EXPRESSION
    assert request.lookback_years == 2
    assert request.horizon == 20
    assert request.rank_feature == "return_20"
    assert request.descending is True
    assert request.fixed_percentages == (0.05,)
    assert request.atr_multiples == (2.0,)
    assert request.entry_slippage_bps == 5.0
    assert request.stop_slippage_bps == 10.0


def test_reconstructs_managed_stop_target_plan_without_legacy_stop_grid() -> None:
    request = strategy_request_from_resolved_configuration(  # type: ignore[arg-type]
        _configuration(managed=True)
    )

    assert request.fixed_percentages == ()
    assert request.atr_multiples == ()
    assert request.same_bar_policy is SameBarExitPolicy.TARGET_FIRST
    assert len(request.managed_exit_plans) == 1
    plan = request.managed_exit_plans[0]
    assert plan.stop_family is ExitFamily.TRAILING_PERCENT_STOP
    assert plan.stop_value == pytest.approx(0.08)
    assert plan.target_family is TargetFamily.ATR_MULTIPLE
    assert plan.target_value == pytest.approx(2.0)


def test_freeze_sweep_candidate_requires_an_already_declared_value() -> None:
    configuration = _configuration(sweep=True)
    request = strategy_request_from_resolved_configuration(configuration)  # type: ignore[arg-type]

    frozen = freeze_entry_sweep_candidate(
        configuration,  # type: ignore[arg-type]
        request,
        30.0,
    )

    assert "__p30__" in frozen.expression
    assert "__p20__" not in frozen.expression
    assert source_declared_entry_sweep_values(configuration) == (10.0, 20.0, 30.0)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="was not part of the source declared sweep"):
        freeze_entry_sweep_candidate(
            configuration,  # type: ignore[arg-type]
            request,
            25.0,
        )
