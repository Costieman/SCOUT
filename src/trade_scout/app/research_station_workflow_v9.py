"""Research Station v9: generalized strategic analysis across Section 5 variables."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from trade_scout.app import research_station_workflow_v8 as _v8
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps

_CONFIGURED = False


def _render_next_steps_v9(report: StrategyBuilderReport) -> str:
    return render_strategic_next_step_html(analyze_strategic_next_steps(report.comparison))


def configure_research_station_runtime() -> None:
    """Preserve v8 behavior while replacing only the strategic renderer with the shared v9 view."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v8._render_next_steps = cast(Callable[[StrategyBuilderReport], str], _render_next_steps_v9)
    _v8.configure_research_station_runtime()
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
