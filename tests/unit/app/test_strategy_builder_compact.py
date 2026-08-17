from __future__ import annotations

from typing import cast

from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_workbench_console import build_research_workbench_response
from trade_scout.app.strategy_builder_compact import STRATEGY_BUILDER_COMPACT_JS
from trade_scout.app.strategy_builder_sweep_controls import STRATEGY_BUILDER_SWEEP_CONTROLS_JS


def test_compact_asset_summarizes_configured_entry_rules() -> None:
    assert "rule-summary" in STRATEGY_BUILDER_COMPACT_JS
    assert "rule-collapsed" in STRATEGY_BUILDER_COMPACT_JS
    assert "Edit" in STRATEGY_BUILDER_COMPACT_JS
    assert "Done" in STRATEGY_BUILDER_COMPACT_JS
    assert "param-period" in STRATEGY_BUILDER_COMPACT_JS
    assert "param-deviations" in STRATEGY_BUILDER_COMPACT_JS


def test_sweep_controls_hide_bound_rows_and_offer_multiple_chart_metrics() -> None:
    assert "display', 'none', 'important'" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS
    assert "controlled by Section 5" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS
    assert "Primary chart metric" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS
    assert "Optional second metric" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS
    assert "P05 / 5th-percentile return" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS
    assert "Profit factor" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS
    assert "Average holding period" in STRATEGY_BUILDER_SWEEP_CONTROLS_JS


def test_workbench_serves_compact_and_sweep_control_assets() -> None:
    config = cast(LocalConsoleConfig, object())
    compact = build_research_workbench_response(
        "/assets/strategy-builder-compact.js",
        config,
    )
    sweep = build_research_workbench_response(
        "/assets/strategy-builder-sweep-controls.js",
        config,
    )

    assert compact.status_code == 200
    assert compact.body.decode("utf-8") == STRATEGY_BUILDER_COMPACT_JS
    assert sweep.status_code == 200
    assert sweep.body.decode("utf-8") == STRATEGY_BUILDER_SWEEP_CONTROLS_JS
