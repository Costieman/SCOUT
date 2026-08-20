from trade_scout.app.strategy_next_step import analyze_strategic_next_steps
from trade_scout.risk.exit_policies import ExitFamily
from trade_scout.statistics.exit_research import ExitPolicySummary, ExitResearchComparison


def _summary(
    family: ExitFamily,
    *,
    expectancy: float,
    distance_pct: float | None = None,
    stop_out_rate: float = 0.0,
) -> ExitPolicySummary:
    parameters = {} if distance_pct is None else {"distance_pct": distance_pct}
    return ExitPolicySummary(
        policy_id=f"{family.value}:{distance_pct}",
        policy_version="test-v1",
        family=family,
        resolved_parameters=parameters,
        target_family=None,
        target_parameters={},
        sample_size=930,
        stop_out_count=int(stop_out_rate * 930),
        stop_out_rate=stop_out_rate,
        target_hit_count=0,
        target_hit_rate=0.0,
        same_bar_ambiguous_count=0,
        same_bar_ambiguous_rate=0.0,
        expectancy=expectancy,
        expectancy_delta_vs_hold=None,
        median_return=expectancy,
        win_probability=0.5,
        average_winner=0.2,
        average_loser=-0.1,
        payoff_ratio=2.0,
        profit_factor=2.0,
        tail_loss_p05=-0.2,
        average_holding_period_sessions=100.0,
        median_holding_period_sessions=80.0,
        median_mae_before_exit=-0.1,
        median_mfe_full_horizon=0.2,
        median_max_drawdown_before_exit=-0.15,
        gap_through_frequency=0.0,
        mean_gap_loss_pct=None,
        mean_cost_drag_return=0.0,
    )


def _comparison(*rows: ExitPolicySummary) -> ExitResearchComparison:
    return ExitResearchComparison(
        horizon=252,
        complete_event_count=930,
        event_population_fingerprint="fixture",
        policy_summaries=rows,
        warnings=(),
    )


def test_boundary_limited_wide_stop_sweep_proposes_wider_and_ultra_tight_branches() -> None:
    hold = _summary(ExitFamily.HOLD_TO_HORIZON, expectancy=0.1624)
    rows = tuple(
        _summary(
            ExitFamily.FIXED_PERCENT_STOP,
            expectancy=expectancy,
            distance_pct=distance,
            stop_out_rate=stop_rate,
        )
        for distance, expectancy, stop_rate in (
            (0.05, 0.0268, 0.887),
            (0.10, 0.0341, 0.765),
            (0.15, 0.0428, 0.646),
            (0.20, 0.0769, 0.463),
            (0.25, 0.1278, 0.318),
        )
    )

    analysis = analyze_strategic_next_steps(_comparison(hold, *rows))

    assert "Wider stops" in analysis.headline
    assert "boundary-limited" in analysis.observation
    assert "25% to 50%" in analysis.options[0].proposed_range
    assert "1% to 5%" in analysis.options[1].proposed_range
    assert "hypothesis" in analysis.caution


def test_interior_peak_proposes_local_resolution_not_boundary_extension() -> None:
    hold = _summary(ExitFamily.HOLD_TO_HORIZON, expectancy=0.10)
    rows = tuple(
        _summary(ExitFamily.FIXED_PERCENT_STOP, expectancy=value, distance_pct=distance)
        for distance, value in (
            (0.05, 0.03),
            (0.10, 0.06),
            (0.15, 0.08),
            (0.20, 0.06),
            (0.25, 0.04),
        )
    )

    analysis = analyze_strategic_next_steps(_comparison(hold, *rows))

    assert "interior" in analysis.headline.lower()
    assert len(analysis.options) == 1
    assert "Resolve the local optimum" == analysis.options[0].title
