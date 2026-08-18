from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_clean_defaults import STRATEGY_BUILDER_CLEAN_DEFAULTS_JS


def test_clean_defaults_asset_only_targets_fresh_strategy_builder_load() -> None:
    assert "window.location.pathname !== '/research/strategy'" in STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
    assert "window.location.search" in STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
    assert "No entry conditions selected" in STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
    assert "No managed exit plans selected" in STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
    assert "protective stop plan" in STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
    assert "signalLimit.value = '500'" in STRATEGY_BUILDER_CLEAN_DEFAULTS_JS


def test_workbench_serves_clean_defaults_asset_without_analytical_sources() -> None:
    response = build_research_workbench_response(
        "/assets/strategy-builder-clean-defaults.js",
        cast(LocalConsoleConfig, object()),
    )

    assert response.status_code == 200
    assert response.content_type == "text/javascript; charset=utf-8"
    assert response.body.decode("utf-8") == STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
    assert any(
        name == "Content-Security-Policy" and "script-src 'self'" in value
        for name, value in response.headers
    )
