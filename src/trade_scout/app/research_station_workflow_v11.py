"""Research Station v11: research-order guidance plus inactivity-aware iteration."""

from __future__ import annotations

from html import escape

from trade_scout.app import research_station_workflow_v8 as _v8
from trade_scout.app import research_station_workflow_v10 as _v10
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.research_sequence_guidance import guide_research_sequence
from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps

_CONFIGURED = False


def _render_next_steps_v11(report: StrategyBuilderReport) -> str:
    analysis = analyze_strategic_next_steps(report.comparison)
    followup = build_exit_followup(report.comparison)
    sequence = guide_research_sequence(report.comparison)
    guidance = (
        '<div class="strategic-next-step-observation" style="border-left-color:#b99cff">'
        "<strong>Recommended research order:</strong><br>"
        f"<strong>{escape(sequence.headline)}</strong> {escape(sequence.rationale)} "
        f'<br><span class="subtle">Next dimension: {escape(sequence.next_dimension)}</span></div>'
    )
    rendered = render_strategic_next_step_html(analysis, followup)
    marker = '<div class="strategic-next-step-options">'
    return rendered.replace(marker, guidance + marker, 1)


def configure_research_station_runtime() -> None:
    """Install v10 and add advisory research-stage guidance."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v10.configure_research_station_runtime()
    _v8._render_next_steps = _render_next_steps_v11
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
