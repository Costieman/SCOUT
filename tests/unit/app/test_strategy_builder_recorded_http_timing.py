from trade_scout.app.strategy_builder_recorded_http import _strategy_performance_lines
from trade_scout.app.strategy_builder_service import StrategyBuilderPerformance


def test_strategy_performance_lines_expose_phase_and_total_timings() -> None:
    performance = StrategyBuilderPerformance(
        dataset_daily_bar_count=1000,
        canonical_daily_bar_count=800,
        working_daily_bar_count=600,
        phase_seconds=(
            ("materialize requested indicators", 1.23456),
            ("select frozen entry population", 0.25),
            ("evaluate exit policies", 2.5),
        ),
        total_seconds=4.0,
    )

    lines = _strategy_performance_lines(performance)

    assert lines[0] == "Strategy Builder timing | bars dataset=1000 canonical=800 working=600"
    assert "materialize requested indicators: 1.235s" in lines[1]
    assert "select frozen entry population: 0.250s" in lines[2]
    assert "evaluate exit policies: 2.500s" in lines[3]
    assert lines[-1] == "Strategy Builder timing | TOTAL: 4.000s"
