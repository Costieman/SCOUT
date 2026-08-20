from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.risk.exit_policies import ExitFamily, TargetFamily
from trade_scout.statistics.exit_research import ExitPolicySummary, ExitResearchComparison


def _row(target: float, expectancy: float, hit: float) -> ExitPolicySummary:
    return ExitPolicySummary(
        policy_id=str(target), policy_version="v1", family=ExitFamily.FIXED_PERCENT_STOP,
        resolved_parameters={"distance_pct": 0.05}, target_family=TargetFamily.FIXED_PERCENT,
        target_parameters={"gain_pct": target}, sample_size=2892, stop_out_count=1420,
        stop_out_rate=0.491, target_hit_count=int(hit * 2892), target_hit_rate=hit,
        same_bar_ambiguous_count=0, same_bar_ambiguous_rate=0.0, expectancy=expectancy,
        expectancy_delta_vs_hold=None, median_return=0.0, win_probability=0.42,
        average_winner=0.1, average_loser=-0.05, payoff_ratio=2.0, profit_factor=1.4,
        tail_loss_p05=-0.055, average_holding_period_sessions=13.7,
        median_holding_period_sessions=20.0, median_mae_before_exit=-0.04,
        median_mfe_full_horizon=0.08, median_max_drawdown_before_exit=-0.05,
        gap_through_frequency=0.0, mean_gap_loss_pct=None, mean_cost_drag_return=0.0,
    )


def test_rarely_hit_flat_profit_target_range_is_declared_inactive() -> None:
    rows = tuple(
        _row(target, expectancy, hit)
        for target, expectancy, hit in (
            (0.30, 0.0110, 0.029), (0.35, 0.0117, 0.023), (0.40, 0.0115, 0.017),
            (0.45, 0.0115, 0.012), (0.50, 0.0114, 0.007), (0.55, 0.0112, 0.005),
        )
    )
    comparison = ExitResearchComparison(
        horizon=20, complete_event_count=2892, event_population_fingerprint="fixture",
        policy_summaries=rows, warnings=(),
    )
    plan = build_exit_followup(comparison)
    assert plan is not None
    assert plan.status == "inactive_target_range"
    assert not plan.can_run
    assert "2.9%" in plan.message
    assert "maximum holding horizon" in plan.message
