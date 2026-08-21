# ruff: noqa: E501
"""Research Station v12: use active Research Brain history to guide the next research stage."""

from __future__ import annotations

import json
from hashlib import sha256
from http import HTTPStatus
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from trade_scout.app import research_station_workflow_v8 as _v8
from trade_scout.app import research_station_workflow_v11 as _v11
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_sequence_guidance import guide_research_sequence_from_brain
from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps
from trade_scout.experiments.research_brains import BrainExperimentMembership, FileResearchBrainStore

_CONFIGURED = False
_GUIDANCE_PATH = "/research/brain-guidance"
_GUIDANCE_CACHE: dict[str, tuple[str, dict[str, str]]] = {}
_GUIDANCE_LOCK = Lock()
_BRAIN_SERVICE: ResearchBrainWorkbenchService | None = None
_BRAIN_STORE: FileResearchBrainStore | None = None
_ORIGINAL_BUILD_RESPONSE = _console.build_research_workbench_response


def _render_next_steps_v12(report: StrategyBuilderReport) -> str:
    analysis = analyze_strategic_next_steps(report.comparison)
    followup = build_exit_followup(report.comparison)
    rendered = render_strategic_next_step_html(analysis, followup)
    guidance = (
        '<div id="research-sequence-guidance" class="strategic-next-step-observation" '
        'style="border-left-color:#b99cff">'
        "<strong>Recommended research order:</strong><br>"
        '<strong id="research-sequence-headline">Use the active Research Brain to choose the next stage.</strong> '
        '<span id="research-sequence-rationale">SCOUT will load guidance only for the active Brain.</span>'
        '<br><span class="subtle">Next dimension: '
        '<span id="research-sequence-next">Select or continue from a Research Brain.</span></span></div>'
    )
    marker = '<div class="strategic-next-step-options">'
    return rendered.replace(marker, guidance + marker, 1)


def configure_research_station_runtime(*, experiment_root: Path, brain_root: Path) -> None:
    """Install v11 and configure lazy Brain guidance without startup indexing."""

    global _BRAIN_SERVICE, _BRAIN_STORE, _CONFIGURED
    if _CONFIGURED:
        return
    _v11.configure_research_station_runtime()
    _v8._render_next_steps = _render_next_steps_v12
    _BRAIN_SERVICE = ResearchBrainWorkbenchService(
        experiment_root=experiment_root,
        brain_root=brain_root,
    )
    _BRAIN_STORE = FileResearchBrainStore(brain_root)
    _console.build_research_workbench_response = _build_research_workbench_response_v12
    _install_brain_guidance_asset()
    _CONFIGURED = True


def _build_research_workbench_response_v12(
    request_target: str,
    config: _console.LocalConsoleConfig,
    *,
    experiment_recorder: object | None = None,
) -> _console.ConsoleResponse:
    """Serve the lazy Brain-guidance endpoint; delegate every other route unchanged."""

    if urlsplit(request_target).path == _GUIDANCE_PATH:
        return _build_brain_guidance_response(request_target)
    return _ORIGINAL_BUILD_RESPONSE(
        request_target,
        config,
        experiment_recorder=experiment_recorder,
    )


def _build_brain_guidance_response(request_target: str) -> _console.ConsoleResponse:
    service = _BRAIN_SERVICE
    store = _BRAIN_STORE
    if service is None or store is None:
        return _json_response(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"error": "Brain guidance is not configured."},
        )
    parameters = parse_qs(urlsplit(request_target).query, keep_blank_values=True)
    raw_brain_ids = parameters.get("brain", [])
    brain_id = raw_brain_ids[0].strip() if len(raw_brain_ids) == 1 else ""
    if not brain_id:
        return _json_response(HTTPStatus.BAD_REQUEST, {"error": "brain is required"})
    try:
        snapshot = store.snapshot(brain_id)
        fingerprint = _membership_fingerprint(snapshot.memberships)
        with _GUIDANCE_LOCK:
            cached = _GUIDANCE_CACHE.get(brain_id)
            if cached is not None and cached[0] == fingerprint:
                return _json_response(HTTPStatus.OK, cached[1])
            view = service.detail(brain_id)
            recommendation = guide_research_sequence_from_brain(view)
            payload = {
                "brain_id": brain_id,
                "stage": recommendation.stage,
                "headline": recommendation.headline,
                "rationale": recommendation.rationale,
                "next_dimension": recommendation.next_dimension,
                "membership_fingerprint": fingerprint,
            }
            _GUIDANCE_CACHE[brain_id] = (fingerprint, payload)
        return _json_response(HTTPStatus.OK, payload)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        return _json_response(
            HTTPStatus.BAD_REQUEST,
            {"error": f"{type(exc).__name__}: {exc}"},
        )


def _membership_fingerprint(memberships: tuple[BrainExperimentMembership, ...]) -> str:
    """Fingerprint only Brain membership inputs that can invalidate strategic guidance."""

    identity = tuple(
        sorted(
            (
                item.membership_id,
                item.experiment_id,
                item.experiment_manifest_checksum,
                item.experiment_status.value,
            )
            for item in memberships
        )
    )
    encoded = json.dumps(identity, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256(encoded).hexdigest()


def _json_response(status: HTTPStatus, payload: dict[str, str]) -> _console.ConsoleResponse:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _console.ConsoleResponse(
        status_code=status,
        content_type="application/json; charset=utf-8",
        body=body,
        headers=_console._interactive_security_headers(),
    )


def _install_brain_guidance_asset() -> None:
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    current = str(namespace[asset_name])
    marker = "trade-scout:on-demand-brain-guidance-v12"
    if marker in current:
        return
    namespace[asset_name] = current + "\n" + _brain_guidance_js()


def _brain_guidance_js() -> str:
    return """
(() => {
  "use strict";
  // trade-scout:on-demand-brain-guidance-v12
  if (window.location.pathname !== "/research/strategy") return;
  const activeKey = "trade-scout:research-brain:active";
  const urlBrain = (new URL(window.location.href).searchParams.get("brain") || "").trim();
  if (urlBrain) localStorage.setItem(activeKey, urlBrain);
  const brainId = urlBrain || (localStorage.getItem(activeKey) || "").trim();
  const headline = document.getElementById("research-sequence-headline");
  const rationale = document.getElementById("research-sequence-rationale");
  const next = document.getElementById("research-sequence-next");
  const host = document.getElementById("research-sequence-guidance");
  if (!headline || !rationale || !next || !host) return;
  if (!brainId) {
    rationale.textContent = "No active Research Brain is selected, so SCOUT will not infer completed stages from unrelated runs.";
    return;
  }
  headline.textContent = "Loading active Brain guidance...";
  rationale.textContent = "SCOUT is analyzing only the selected Brain; unrelated Brains are not loaded.";
  next.textContent = "Waiting for active Brain analysis.";
  fetch(`/research/brain-guidance?brain=${encodeURIComponent(brainId)}`, {
    headers: {"Accept": "application/json"},
    cache: "no-store",
  })
    .then((response) => response.json().then((payload) => ({response, payload})))
    .then(({response, payload}) => {
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      headline.textContent = payload.headline;
      rationale.textContent = payload.rationale;
      next.textContent = payload.next_dimension;
      host.dataset.researchStage = payload.stage;
      host.dataset.membershipFingerprint = payload.membership_fingerprint;
    })
    .catch((error) => {
      headline.textContent = "Brain guidance is unavailable for this request.";
      rationale.textContent = String(error && error.message ? error.message : error);
      next.textContent = "The rest of Strategy Builder remains available.";
    });
})();
"""


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
