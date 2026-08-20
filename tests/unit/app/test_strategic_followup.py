from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.risk.exit_policies import ExitFamily, TargetFamily
from trade_scout.statistics.exit_research import ExitPolicySummary, ExitResearchComparison


def _summary(
    family: ExitFamily,
    *,
    expectancy: float,
    distance_pct: float | None = None,
    target_family: TargetFamily | None = None,
    target_value: float | None = None,
    target_hit_rate: float = 0.0,
) -> ExitPolicySummary:
    resolved = {} if distance_pct is None else {"distance_pct": distance_pct}
    targets = {}
    if target_family is TargetFamily.FIXED_PERCENT and target_value is not None:
        targets["gain_pct"] = target_value
    return ExitPolicySummary(
        policy_id=f"{family}:{distance_pct}:{target_family}:{target_value}",
        policy_version="test-v1",
        family=family,
        resolved_parameters=resolved,
        target_family=target_family,
        target_parameters=targets,
        sample_size=1000,
        stop_out_count=0,
        stop_out_rate=0.0,
        target_hit_count=int(target_hit_rate * 1000),
        target_hit_rate=target_hit_rate,
        same_bar_ambiguous_count=0,
        same_bar_ambiguous_rate=0.0,
        expectancy=expectancy,
        expectancy_delta_vs_hold=None,
        median_return=expectancy,
        win_probability=0.5,
        average_winner=0.1,
        average_loser=-0.05,
        payoff_ratio=2.0,
        profit_factor=1.5,
        tail_loss_p05=-0.1,
        average_holding_period_sessions=10.0,
        median_holding_period_sessions=10.0,
        median_mae_before_exit=-0.05,
        median_mfe_full_horizon=0.1,
        median_max_drawdown_before_exit=-0.1,
        gap_through_frequency=0.0,
        mean_gap_loss_pct=None,
        mean_cost_drag_return=0.0,
    )


def _comparison(*rows: ExitPolicySummary) -> ExitResearchComparison:
    return ExitResearchComparison(
        horizon=10,
        complete_event_count=1000,
        event_population_fingerprint="fixture",
        policy_summaries=rows,
        warnings=(),
    )


def test_flat_profit_target_surface_below_hold_stops_honing() -> None:
    hold = _summary(ExitFamily.HOLD_TO_HORIZON, expectancy=0.0106)
    managed = tuple(
        _summary(
            ExitFamily.FIXED_PERCENT_STOP,
            expectancy=expectancy,
            distance_pct=0.05,
            target_family=TargetFamily.FIXED_PERCENT,
            target_value=target / 100.0,
            target_hit_rate=0.20,
        )
        for target, expectancy in (
            (5, 0.0056),
            (10, 0.0065),
            (15, 0.0067),
            (20, 0.0065),
            (25, 0.0062),
            (30, 0.0059),
        )
    )

    plan = build_exit_followup(_comparison(hold, *managed))

    assert plan is not None
    assert plan.status == "control_dominated_flat"
    assert not plan.can_run
    assert "Stop honing this variable" in plan.message
    assert "P05" in plan.message


def test_boundary_sweep_produces_machine_action_for_same_variable() -> None:
    hold = _summary(ExitFamily.HOLD_TO_HORIZON, expectancy=0.20)
    managed = tuple(
        _summary(
            ExitFamily.FIXED_PERCENT_STOP,
            expectancy=value,
            distance_pct=distance / 100.0,
        )
        for distance, value in ((5, 0.02), (10, 0.04), (15, 0.07), (20, 0.11), (25, 0.15))
    )

    plan = build_exit_followup(_comparison(hold, *managed))

    assert plan is not None
    assert plan.can_run
    assert plan.sweep_variable == "fixed"
    assert plan.from_value == 25
    assert plan.to_value == 50
    assert plan.step_value == 5
