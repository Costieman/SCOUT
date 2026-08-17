from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_readout import STRATEGY_BUILDER_READOUT_JS


def test_readout_asset_uses_calibrated_traffic_light_language() -> None:
    assert "GREEN · Positive" in STRATEGY_BUILDER_READOUT_JS
    assert "ORANGE · Caution" in STRATEGY_BUILDER_READOUT_JS
    assert "RED · Negative" in STRATEGY_BUILDER_READOUT_JS
    assert "not a validation score" in STRATEGY_BUILDER_READOUT_JS
    assert "not annualized portfolio return or a forecast" in STRATEGY_BUILDER_READOUT_JS
    assert "±0.25-point traffic-light boundary" in STRATEGY_BUILDER_READOUT_JS
    assert "one parameter at a time" in STRATEGY_BUILDER_READOUT_JS


def test_workbench_serves_readout_asset_without_analytical_sources() -> None:
    response = build_research_workbench_response(
        "/assets/strategy-builder-readout.js",
        cast(LocalConsoleConfig, object()),
    )

    assert response.status_code == 200
    assert response.content_type == "text/javascript; charset=utf-8"
    assert response.body.decode("utf-8") == STRATEGY_BUILDER_READOUT_JS
