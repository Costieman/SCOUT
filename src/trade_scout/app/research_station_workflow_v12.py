# ruff: noqa: E501
"""Research Station v12: query current Research Brain intelligence on demand."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlsplit

from trade_scout.app import research_station_workflow_v8 as _v8
from trade_scout.app import research_station_workflow_v11 as _v11
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.local_console import ConsoleResponse, LocalConsoleConfig
from trade_scout.app.research_brain_intelligence_http import build_research_brain_intelligence_json
from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps

_CONFIGURED = False
_INTELLIGENCE_PATH = "/research/brains/intelligence"
_BASE_BUILD_RESPONSE = _console.build_research_workbench_response


def _render_next_steps_v12(report: StrategyBuilderReport) -> str:
    analysis = analyze_strategic_next_steps(report.comparison)
    followup = build_exit_followup(report.comparison)
    rendered = render_strategic_next_step_html(analysis, followup)
    guidance = (
        '<div id="research-sequence-guidance" class="strategic-next-step-observation" '
        'style="border-left-color:#b99cff">'
        "<strong>Recommended research order:</strong><br>"
        '<strong id="research-sequence-headline">Use the active Research Brain to choose the next stage.</strong> '
        '<span id="research-sequence-rationale">SCOUT will read the Brain\'s current preserved evidence.</span>'
        '<br><span class="subtle">Next dimension: '
        '<span id="research-sequence-next">Select or continue from a Research Brain.</span></span></div>'
    )
    marker = '<div class="strategic-next-step-options">'
    return rendered.replace(marker, guidance + marker, 1)


def configure_research_station_runtime(*, experiment_root, brain_root) -> None:
    """Install live Brain guidance without pre-indexing Brain state at server startup."""

    del experiment_root, brain_root
    global _CONFIGURED
    if _CONFIGURED:
        return
    _v11.configure_research_station_runtime()
    _v8._render_next_steps = _render_next_steps_v12
    _console.build_research_workbench_response = _build_live_research_response
    _install_live_brain_guidance_asset()
    _CONFIGURED = True


def _build_live_research_response(
    request_target: str,
    config: LocalConsoleConfig,
    *,
    experiment_recorder: StrategyBuilderExperimentRecorder | None = None,
) -> ConsoleResponse:
    """Serve the read-only live intelligence endpoint before delegating normal workbench GETs."""

    parsed = urlsplit(request_target)
    if parsed.path != _INTELLIGENCE_PATH:
        return _BASE_BUILD_RESPONSE(
            request_target,
            config,
            experiment_recorder=experiment_recorder,
        )
    if experiment_recorder is None:
        return ConsoleResponse(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json; charset=utf-8",
            body=b'{"error":"Research Brain intelligence is not configured"}',
            headers=(("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")),
        )
    try:
        status, payload = build_research_brain_intelligence_json(parsed.query, experiment_recorder)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        status = HTTPStatus.BAD_REQUEST
        payload = '{"error":' + _json_string(str(exc)) + "}"
    return ConsoleResponse(
        status_code=status,
        content_type="application/json; charset=utf-8",
        body=payload.encode("utf-8"),
        headers=(("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")),
    )


def _json_string(value: str) -> str:
    import json

    return json.dumps(value)


def _install_live_brain_guidance_asset() -> None:
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    current = str(namespace[asset_name])
    marker = "trade-scout:live-brain-intelligence-v13"
    if marker in current:
        return
    namespace[asset_name] = current + "\n" + _live_brain_guidance_js()


def _live_brain_guidance_js() -> str:
    return r'''
(() => {
  "use strict";
  // trade-scout:live-brain-intelligence-v13
  if (window.location.pathname !== "/research/strategy") return;
  const activeKey = "trade-scout:research-brain:active";
  const urlBrain = (new URL(window.location.href).searchParams.get("brain") || "").trim();
  if (urlBrain) localStorage.setItem(activeKey, urlBrain);

  const elements = () => ({
    headline: document.getElementById("research-sequence-headline"),
    rationale: document.getElementById("research-sequence-rationale"),
    next: document.getElementById("research-sequence-next"),
    host: document.getElementById("research-sequence-guidance"),
  });

  async function refreshBrainIntelligence() {
    const {headline, rationale, next, host} = elements();
    if (!headline || !rationale || !next || !host) return;
    const brainId = (new URL(window.location.href).searchParams.get("brain") || localStorage.getItem(activeKey) || "").trim();
    if (!brainId) {
      rationale.textContent = "No active Research Brain is selected, so SCOUT will not infer completed stages from unrelated runs.";
      return;
    }
    try {
      const response = await fetch(`/research/brains/intelligence?brain=${encodeURIComponent(brainId)}`, {
        method: "GET",
        cache: "no-store",
        headers: {"Accept": "application/json"},
      });
      const item = await response.json();
      if (!response.ok) throw new Error(item.error || `HTTP ${response.status}`);
      headline.textContent = item.guidance.headline;
      rationale.textContent = item.guidance.rationale;
      next.textContent = item.guidance.next_dimension;
      host.dataset.researchStage = item.guidance.stage;
      host.dataset.evidenceRevision = item.evidence_revision;
      host.dataset.brainExperimentCount = String(item.experiment_count);
    } catch (error) {
      headline.textContent = "Current Brain guidance could not be loaded.";
      rationale.textContent = `SCOUT did not substitute stale startup guidance: ${String(error)}`;
      next.textContent = "Inspect the Brain evidence, then retry.";
      delete host.dataset.researchStage;
    }
  }

  window.addEventListener("pageshow", refreshBrainIntelligence);
  window.addEventListener("focus", refreshBrainIntelligence);
  window.addEventListener("storage", (event) => {
    if (event.key === activeKey) refreshBrainIntelligence();
  });
  document.addEventListener("trade-scout:brain-evidence-changed", refreshBrainIntelligence);
  refreshBrainIntelligence();
})();
'''


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
