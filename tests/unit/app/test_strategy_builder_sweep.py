from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_sweep import STRATEGY_BUILDER_SWEEP_JS


def test_sweep_asset_limits_research_to_one_exit_parameter() -> None:
    assert "Research variable — one-variable sweep" in STRATEGY_BUILDER_SWEEP_JS
    assert "Fixed stop distance (%)" in STRATEGY_BUILDER_SWEEP_JS
    assert "Trailing stop distance (%)" in STRATEGY_BUILDER_SWEEP_JS
    assert "ATR stop multiple" in STRATEGY_BUILDER_SWEEP_JS
    assert "Trailing ATR multiple" in STRATEGY_BUILDER_SWEEP_JS
    assert "limited to 60 tested values" in STRATEGY_BUILDER_SWEEP_JS
    assert "Every value will be retained" in STRATEGY_BUILDER_SWEEP_JS
    assert "same frozen entry population" in STRATEGY_BUILDER_SWEEP_JS


def test_sweep_asset_visualizes_expectancy_without_calling_it_a_validated_optimum() -> None:
    assert "Read the shape, not just the peak" in STRATEGY_BUILDER_SWEEP_JS
    assert "Expectancy per trade" in STRATEGY_BUILDER_SWEEP_JS
    assert "not a validated optimum" in STRATEGY_BUILDER_SWEEP_JS
    assert "Delta vs hold" in STRATEGY_BUILDER_SWEEP_JS
    assert "P05" in STRATEGY_BUILDER_SWEEP_JS


def test_workbench_serves_sweep_asset_without_analytical_sources() -> None:
    response = build_research_workbench_response(
        "/assets/strategy-builder-sweep.js",
        cast(LocalConsoleConfig, object()),
    )

    assert response.status_code == 200
    assert response.content_type == "text/javascript; charset=utf-8"
    assert response.body.decode("utf-8") == STRATEGY_BUILDER_SWEEP_JS
