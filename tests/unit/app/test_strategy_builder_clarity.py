from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_clarity import STRATEGY_BUILDER_CLARITY_JS


def test_clarity_asset_documents_execution_and_forced_horizon_semantics() -> None:
    assert "SCOUT baseline — liquid US equities" in STRATEGY_BUILDER_CLARITY_JS
    assert "entry: 5, exit: 5, stop: 10, commission: 0" in STRATEGY_BUILDER_CLARITY_JS
    assert "Maximum holding period (forced exit)" in STRATEGY_BUILDER_CLARITY_JS
    assert "not merely a reporting window" in STRATEGY_BUILDER_CLARITY_JS
    assert "ma_above" in STRATEGY_BUILDER_CLARITY_JS
    assert "No 0/1 value needs to be entered" in STRATEGY_BUILDER_CLARITY_JS


def test_workbench_serves_clarity_asset_without_analytical_sources() -> None:
    response = build_research_workbench_response(
        "/assets/strategy-builder-clarity.js",
        cast(LocalConsoleConfig, object()),
    )

    assert response.status_code == 200
    assert response.content_type == "text/javascript; charset=utf-8"
    assert response.body.decode("utf-8") == STRATEGY_BUILDER_CLARITY_JS
    assert any(
        name == "Content-Security-Policy" and "script-src 'self'" in value
        for name, value in response.headers
    )
