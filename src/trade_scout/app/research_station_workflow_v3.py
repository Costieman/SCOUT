# ruff: noqa: E501
"""Third-pass Research Station execution repair.

The suite-preview route deliberately uses ``load_only=1``. This layer makes the subsequent Run
Research action unambiguous: an explicit execute marker always wins over preview state, the run
button submits through the normal composer event pipeline, and the selected entry family is kept
consistent with the loaded suite rather than silently falling back to feature-expression mode.
"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlencode

from trade_scout.app import research_station_workflow_v2 as _v2
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder

_CONFIGURED = False


def _one(parameters: dict[str, list[str]], name: str, *, default: str = "") -> str:
    values = parameters.get(name)
    if not values:
        return default
    return values[-1]


def _without_runtime_markers(query: str) -> str:
    parameters = parse_qs(query, keep_blank_values=True)
    parameters.pop("load_only", None)
    parameters.pop("execute_run", None)
    pairs: list[tuple[str, str]] = []
    for key, values in parameters.items():
        pairs.extend((key, value) for value in values)
    return urlencode(pairs)


def _recorded_page_with_explicit_execute(
    query: str,
    config: LocalConsoleConfig,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Treat an explicit Run action as execution even when the page originated as a preview."""

    parameters = parse_qs(query, keep_blank_values=True)
    if _one(parameters, "execute_run") == "1":
        return _v2._ORIGINAL_RECORDED_PAGE(_without_runtime_markers(query), config, recorder)
    return _v2._recorded_page_with_configuration_preview(query, config, recorder)


_RESEARCH_STATION_V3_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const form = document.getElementById("strategy-form");
  if (!form) return;

  // A loaded structural suite must keep its actual entry family when the operator presses Run.
  // The base renderer historically hard-coded feature_expression in this hidden control.
  const requestedFamily = new URL(window.location.href).searchParams.get("entry_family");
  const entryFamily = form.querySelector('input[name="entry_family"]');
  if (requestedFamily && entryFamily) entryFamily.value = requestedFamily;

  const ensureExecuteMarker = () => {
    let marker = form.querySelector('input[name="execute_run"]');
    if (!marker) {
      marker = document.createElement("input");
      marker.type = "hidden";
      marker.name = "execute_run";
      form.append(marker);
    }
    marker.value = "1";
  };

  // Capture submission after all editable controls are prepared. The backend gives this marker
  // precedence over load_only, so a suite preview can never swallow an intentional research run.
  form.addEventListener("submit", () => ensureExecuteMarker(), true);

  const installExplicitRunAction = () => {
    const dock = document.getElementById("strategy-run-dock");
    const run = dock?.querySelector("button.primary");
    if (!dock || !run || run.dataset.explicitRun === "1") return;
    run.dataset.explicitRun = "1";
    run.type = "button";

    let status = dock.querySelector(".run-submit-status");
    if (!status) {
      status = document.createElement("div");
      status.className = "run-submit-status";
      status.style.cssText = "font-size:12px;color:#98a6b8;min-width:150px;text-align:right";
      dock.insertBefore(status, run);
    }

    run.addEventListener("click", () => {
      ensureExecuteMarker();
      if (!form.reportValidity()) {
        status.textContent = "Fix the highlighted field before running.";
        return;
      }
      status.textContent = "Starting research…";
      run.disabled = true;
      run.textContent = "Running…";

      const submitter = document.createElement("button");
      submitter.type = "submit";
      submitter.hidden = true;
      submitter.tabIndex = -1;
      form.append(submitter);
      form.requestSubmit(submitter);
      queueMicrotask(() => submitter.remove());

      // If another client-side validator cancels submission, restore the action instead of leaving
      // a dead-looking button. A real navigation/run will replace the page before this fires.
      window.setTimeout(() => {
        if (document.visibilityState === "visible") {
          run.disabled = false;
          run.textContent = "Run research";
          if (status.textContent === "Starting research…") {
            status.textContent = "Run was blocked before reaching the backend; check the message above.";
          }
        }
      }, 1200);
    });
  };

  installExplicitRunAction();
})();
"""


def configure_research_station_runtime() -> None:
    """Install v1/v2 repairs plus explicit preview-to-run execution semantics."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v2.configure_research_station_runtime()
    _console.build_recorded_strategy_page = (  # type: ignore[attr-defined]
        _recorded_page_with_explicit_execute
    )
    asset = _console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS  # type: ignore[attr-defined]
    if "execute_run" not in asset:
        _console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS = (  # type: ignore[attr-defined]
            asset + "\n" + _RESEARCH_STATION_V3_JS
        )
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
