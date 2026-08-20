# ruff: noqa: E501
"""Research Station strategic next-step analysis for completed Strategy Builder runs.

This layer preserves the v7 validation/run path and adds a deterministic post-run research-analysis
popup. Suggestions describe what parameter direction the completed evidence supports testing next;
they do not alter the configuration or automatically launch another experiment.
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import cast

from trade_scout.app import research_station_workflow_v7 as _v7
from trade_scout.app import research_workbench_console as _console
from trade_scout.app import strategy_builder_surface as _surface
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps

_CONFIGURED = False
_ORIGINAL_RENDER_REPORT: Callable[[StrategyBuilderReport], str] | None = None

_STRATEGIC_NEXT_STEP_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const modal = document.getElementById("strategic-next-step-modal");
  if (!modal) return;
  const open = document.getElementById("strategic-next-step-open");
  const close = document.getElementById("strategic-next-step-close");
  const dismiss = document.getElementById("strategic-next-step-dismiss");

  const show = () => {
    modal.hidden = false;
    document.body.classList.add("strategic-next-step-modal-open");
    close?.focus();
  };
  const hide = () => {
    modal.hidden = true;
    document.body.classList.remove("strategic-next-step-modal-open");
    open?.focus();
  };

  open?.addEventListener("click", show);
  close?.addEventListener("click", hide);
  dismiss?.addEventListener("click", hide);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) hide();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) hide();
  });

  // A completed run should immediately surface the next research question. The popup never mutates
  // controls and never launches research; the operator decides what, if anything, to test next.
  window.setTimeout(show, 120);
})();
"""


def _render_next_steps(report: StrategyBuilderReport) -> str:
    analysis = analyze_strategic_next_steps(report.comparison)
    options = "".join(
        f"""<article class="strategic-option">
        <h3>{escape(item.title)}</h3>
        <p><strong>Direction:</strong> {escape(item.direction)}</p>
        <p><strong>Suggested next range:</strong> {escape(item.proposed_range)}</p>
        <p><strong>Why:</strong> {escape(item.rationale)}</p>
        <p><strong>What would falsify it:</strong> {escape(item.falsifier)}</p>
        </article>"""
        for item in analysis.options
    )
    if not options:
        options = '<p class="subtle">No directional parameter experiment can be inferred safely from this run yet.</p>'
    return f"""
<style id="strategic-next-step-style">
body.strategic-next-step-modal-open {{ overflow:hidden; }}
.strategic-next-step-summary {{ border-color:#6d5b24 !important; background:linear-gradient(135deg,#17170f,#121720) !important; }}
.strategic-next-step-summary .toolbar {{ margin-top:12px; }}
.strategic-next-step-overlay {{ position:fixed; inset:0; z-index:5000; display:flex; align-items:center; justify-content:center; padding:24px; background:rgba(3,6,10,.78); backdrop-filter:blur(4px); }}
.strategic-next-step-overlay[hidden] {{ display:none; }}
.strategic-next-step-dialog {{ width:min(900px,96vw); max-height:88vh; overflow:auto; border:1px solid #6d5b24; border-radius:14px; background:#121720; box-shadow:0 28px 80px rgba(0,0,0,.5); padding:20px; }}
.strategic-next-step-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }}
.strategic-next-step-head button {{ flex:0 0 auto; }}
.strategic-next-step-observation {{ border-left:3px solid #7fc8ff; background:#10151d; padding:12px 14px; margin:14px 0; }}
.strategic-next-step-options {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:12px; }}
.strategic-option {{ border:1px solid #374252; background:#171d27; border-radius:10px; padding:14px; }}
.strategic-option h3 {{ color:#f1c84b; margin-bottom:10px; }}
.strategic-option p {{ margin:7px 0; }}
.strategic-next-step-caution {{ margin-top:14px; color:#f0c783; font-size:12px; }}
@media(max-width:800px) {{ .strategic-next-step-options {{ grid-template-columns:1fr; }} }}
@media print {{ .strategic-next-step-overlay,.strategic-next-step-summary .toolbar {{ display:none !important; }} }}
</style>
<div class="card s12 strategic-next-step-summary">
  <h2>Strategic next step</h2>
  <p><strong>{escape(analysis.headline)}</strong></p>
  <p class="subtle">{escape(analysis.observation)}</p>
  <div class="toolbar"><button type="button" id="strategic-next-step-open">Review strategic next-step options</button></div>
</div>
<div id="strategic-next-step-modal" class="strategic-next-step-overlay" hidden role="dialog" aria-modal="true" aria-labelledby="strategic-next-step-title">
  <section class="strategic-next-step-dialog">
    <div class="strategic-next-step-head"><div><div class="eyebrow">SCOUT research analysis</div><h2 id="strategic-next-step-title">Strategic next-step options</h2><p><strong>{escape(analysis.headline)}</strong></p></div><button type="button" id="strategic-next-step-close">Close</button></div>
    <div class="strategic-next-step-observation"><strong>What this run is showing:</strong><br>{escape(analysis.observation)}</div>
    <div class="strategic-next-step-options">{options}</div>
    <div class="strategic-next-step-caution">{escape(analysis.caution)}</div>
    <div class="toolbar"><button type="button" id="strategic-next-step-dismiss">Keep researching manually</button></div>
  </section>
</div>
"""


def configure_research_station_runtime() -> None:
    """Install v7, then add deterministic post-run strategic analysis."""

    global _CONFIGURED, _ORIGINAL_RENDER_REPORT
    if _CONFIGURED:
        return
    _v7.configure_research_station_runtime()

    if _ORIGINAL_RENDER_REPORT is None:
        _ORIGINAL_RENDER_REPORT = cast(
            Callable[[StrategyBuilderReport], str], _surface._render_report
        )
        original = _ORIGINAL_RENDER_REPORT

        def render_report_with_next_steps(report: StrategyBuilderReport) -> str:
            return original(report) + _render_next_steps(report)

        _surface._render_report = render_report_with_next_steps

    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    asset = cast(str, namespace[asset_name])
    if "strategic-next-step-modal" not in asset:
        namespace[asset_name] = asset + "\n" + _STRATEGIC_NEXT_STEP_JS
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
