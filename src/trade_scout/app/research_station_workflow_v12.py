# ruff: noqa: E501
"""Research Station v12: use active Research Brain history to guide the next research stage."""

from __future__ import annotations

import json
from pathlib import Path

from trade_scout.app import research_station_workflow_v8 as _v8
from trade_scout.app import research_station_workflow_v11 as _v11
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_sequence_guidance import guide_research_sequence_from_brain
from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps

_CONFIGURED = False
_BRAIN_GUIDANCE: dict[str, dict[str, str]] = {}


def _render_next_steps_v12(report: StrategyBuilderReport) -> str:
    analysis = analyze_strategic_next_steps(report.comparison)
    followup = build_exit_followup(report.comparison)
    rendered = render_strategic_next_step_html(analysis, followup)
    guidance = (
        '<div id="research-sequence-guidance" class="strategic-next-step-observation" '
        'style="border-left-color:#b99cff">'
        "<strong>Recommended research order:</strong><br>"
        '<strong id="research-sequence-headline">Use the active Research Brain to choose the next stage.</strong> '
        '<span id="research-sequence-rationale">SCOUT will compare this run with preserved Brain history.</span>'
        '<br><span class="subtle">Next dimension: '
        '<span id="research-sequence-next">Select or continue from a Research Brain.</span></span></div>'
    )
    marker = '<div class="strategic-next-step-options">'
    return rendered.replace(marker, guidance + marker, 1)


def configure_research_station_runtime(*, experiment_root: Path, brain_root: Path) -> None:
    """Install v11, then add Brain-backed stage guidance for the active strategy session."""

    global _CONFIGURED, _BRAIN_GUIDANCE
    if _CONFIGURED:
        return
    _v11.configure_research_station_runtime()
    service = ResearchBrainWorkbenchService(experiment_root=experiment_root, brain_root=brain_root)
    guidance: dict[str, dict[str, str]] = {}
    for item in service.list_brains():
        try:
            view = service.detail(item.definition.brain_id)
            recommendation = guide_research_sequence_from_brain(view)
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
        guidance[item.definition.brain_id] = {
            "stage": recommendation.stage,
            "headline": recommendation.headline,
            "rationale": recommendation.rationale,
            "next_dimension": recommendation.next_dimension,
        }
    _BRAIN_GUIDANCE = guidance
    _v8._render_next_steps = _render_next_steps_v12
    _install_brain_guidance_asset(guidance)
    _CONFIGURED = True


def _install_brain_guidance_asset(guidance: dict[str, dict[str, str]]) -> None:
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    current = str(namespace[asset_name])
    marker = "trade-scout:brain-aware-research-sequence-v12"
    if marker in current:
        return
    payload = json.dumps(guidance, sort_keys=True, separators=(",", ":"))
    namespace[asset_name] = current + "\n" + _brain_guidance_js(payload)


def _brain_guidance_js(payload: str) -> str:
    return f"""\n(() => {{
  "use strict";
  // trade-scout:brain-aware-research-sequence-v12
  if (window.location.pathname !== "/research/strategy") return;
  const guidance = {payload};
  const activeKey = "trade-scout:research-brain:active";
  const urlBrain = (new URL(window.location.href).searchParams.get("brain") || "").trim();
  if (urlBrain) localStorage.setItem(activeKey, urlBrain);
  const brainId = urlBrain || (localStorage.getItem(activeKey) || "").trim();
  const item = guidance[brainId];
  const headline = document.getElementById("research-sequence-headline");
  const rationale = document.getElementById("research-sequence-rationale");
  const next = document.getElementById("research-sequence-next");
  const host = document.getElementById("research-sequence-guidance");
  if (!headline || !rationale || !next || !host) return;
  if (!brainId) {{
    rationale.textContent = "No active Research Brain is selected, so SCOUT will not infer completed stages from unrelated runs.";
    return;
  }}
  if (!item) {{
    headline.textContent = "The active Research Brain has no readable preserved guidance yet.";
    rationale.textContent = "SCOUT could not resolve its current experiment history at server start.";
    next.textContent = "Open the Brain, verify its experiments, then restart the workbench.";
    return;
  }}
  headline.textContent = item.headline;
  rationale.textContent = item.rationale;
  next.textContent = item.next_dimension;
  host.dataset.researchStage = item.stage;
}})();\n"""


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
