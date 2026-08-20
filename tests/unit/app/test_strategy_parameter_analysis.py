from trade_scout.app.strategy_parameter_analysis import (
    ParameterEvidencePoint,
    analyze_parameter_surface,
)


def _point(
    value: float,
    expectancy: float,
    *,
    n: int = 1000,
    win: float = 0.5,
    pf: float = 1.5,
    p05: float = -0.2,
) -> ParameterEvidencePoint:
    return ParameterEvidencePoint(
        value=value,
        sample_size=n,
        expectancy=expectancy,
        win_probability=win,
        profit_factor=pf,
        tail_loss_p05=p05,
    )


def test_boundary_gradient_extends_range_without_calling_boundary_optimum() -> None:
    analysis = analyze_parameter_surface(
        parameter_label="Bollinger standard deviations",
        unit_label="standard deviations",
        points=(
            _point(1.0, 0.03),
            _point(1.5, 0.04),
            _point(2.0, 0.06),
            _point(2.5, 0.08),
            _point(3.0, 0.10),
        ),
    )

    assert analysis.shape == "increasing"
    assert "above the tested range" in analysis.headline
    assert "3σ" in analysis.options[0].proposed_range
    assert "boundary-limited" in analysis.options[0].rationale


def test_plateau_prefers_region_over_single_historical_winner() -> None:
    analysis = analyze_parameter_surface(
        parameter_label="RSI threshold",
        unit_label="",
        points=(
            _point(25, 0.03),
            _point(30, 0.071, win=0.55, pf=1.8),
            _point(35, 0.075, win=0.56, pf=1.9),
            _point(40, 0.072, win=0.55, pf=1.85),
            _point(45, 0.03),
        ),
    )

    assert analysis.shape == "mixed"
    assert "broad robust region" in analysis.headline
    assert "contiguous cells" in analysis.robustness
    assert "win rate" in analysis.robustness
    assert "profit factor" in analysis.robustness


def test_small_sample_peak_is_explicitly_flagged_as_less_robust() -> None:
    analysis = analyze_parameter_surface(
        parameter_label="Indicator period",
        unit_label="trading days",
        points=(
            _point(10, 0.03, n=1200),
            _point(20, 0.05, n=1100),
            _point(30, 0.09, n=400),
            _point(40, 0.04, n=1000),
        ),
    )

    assert "materially fewer complete observations" in analysis.robustness
    assert "best cell uses 400" in analysis.observation
