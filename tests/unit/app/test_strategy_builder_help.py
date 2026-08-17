from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_help import STRATEGY_BUILDER_HELP_JS


def test_help_asset_defines_plain_english_metric_and_indicator_explanations() -> None:
    assert "Median Maximum Adverse Excursion" in STRATEGY_BUILDER_HELP_JS
    assert "Median Maximum Favorable Excursion" in STRATEGY_BUILDER_HELP_JS
    assert "Average modeled return per trade" in STRATEGY_BUILDER_HELP_JS
    assert "Bollinger Bands" in STRATEGY_BUILDER_HELP_JS
    assert "Relative Strength Index (RSI)" in STRATEGY_BUILDER_HELP_JS
    assert "Right-click for a plain-English explanation" in STRATEGY_BUILDER_HELP_JS
    assert "contextmenu" in STRATEGY_BUILDER_HELP_JS


def test_workbench_serves_help_asset_without_analytical_sources() -> None:
    response = build_research_workbench_response(
        "/assets/strategy-builder-help.js",
        cast(LocalConsoleConfig, object()),
    )

    assert response.status_code == 200
    assert response.content_type == "text/javascript; charset=utf-8"
    assert response.body.decode("utf-8") == STRATEGY_BUILDER_HELP_JS
