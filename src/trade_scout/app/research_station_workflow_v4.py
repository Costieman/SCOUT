# ruff: noqa: E501
"""Deterministic Research Station run submission and operator-visible diagnostics.

The earlier workflow layers separate suite preview from execution and preserve suite entry-family
state. This layer makes the browser-to-backend handoff observable: all existing composer/sweep
submit handlers run first, a final submit observer reports any client-side cancellation, and a valid
request is serialized explicitly to the Strategy Builder GET route. Backend validation errors are
surfaced in a modal on the returned page instead of being easy to miss below the form.
"""

from __future__ import annotations

from typing import cast

from trade_scout.app import research_station_workflow_v3 as _v3
from trade_scout.app import research_workbench_console as _console

_CONFIGURED = False

_RESEARCH_STATION_V4_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const form = document.getElementById("strategy-form");
  if (!form) return;

  const modal = (() => {
    let root = document.getElementById("research-run-diagnostic-modal");
    if (root) return root;
    const style = document.createElement("style");
    style.id = "research-run-diagnostic-style";
    style.textContent = `
      #research-run-diagnostic-modal[hidden] { display:none !important; }
      #research-run-diagnostic-modal { position:fixed; inset:0; z-index:5000; display:grid; place-items:center; padding:22px; background:rgba(3,6,10,.76); }
      #research-run-diagnostic-modal .diagnostic-panel { width:min(720px,96vw); max-height:min(78vh,720px); overflow:auto; border:1px solid #6d5b24; border-radius:14px; background:#121720; box-shadow:0 24px 70px rgba(0,0,0,.55); padding:18px; }
      #research-run-diagnostic-modal h2 { margin:0 0 10px; }
      #research-run-diagnostic-modal .diagnostic-reason { padding:12px; border-left:3px solid #ef7b7b; background:#221315; color:#f4c4c4; white-space:pre-wrap; }
      #research-run-diagnostic-modal .diagnostic-detail { color:#aab5c3; margin-top:10px; white-space:pre-wrap; font-size:12px; }
      #research-run-diagnostic-modal .diagnostic-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:14px; }
    `;
    document.head.append(style);
    root = document.createElement("div");
    root.id = "research-run-diagnostic-modal";
    root.hidden = true;
    root.innerHTML = `<div class="diagnostic-panel" role="dialog" aria-modal="true" aria-labelledby="research-run-diagnostic-title">
      <h2 id="research-run-diagnostic-title">Research did not start</h2>
      <div class="diagnostic-reason"></div>
      <div class="diagnostic-detail"></div>
      <div class="diagnostic-actions"><button type="button" data-close>Close</button></div>
    </div>`;
    document.body.append(root);
    root.querySelector("[data-close]")?.addEventListener("click", () => { root.hidden = true; });
    root.addEventListener("click", (event) => { if (event.target === root) root.hidden = true; });
    return root;
  })();

  const showFailure = (reason, detail = "") => {
    modal.querySelector(".diagnostic-reason").textContent = reason || "The run was cancelled before reaching the research engine.";
    modal.querySelector(".diagnostic-detail").textContent = detail;
    modal.hidden = false;
  };

  const firstComposerError = () => {
    const error = document.getElementById("composer-error");
    if (error && !error.hidden && error.textContent.trim()) return error.textContent.trim();
    const sweep = document.getElementById("sweep-preview");
    if (sweep?.textContent?.trim().startsWith("Fix ")) return sweep.textContent.trim();
    const invalid = [...form.elements].find((node) => node instanceof HTMLElement && "checkValidity" in node && !node.checkValidity());
    if (invalid) {
      const label = invalid.closest("label")?.textContent?.trim() || invalid.getAttribute("name") || "A form field";
      return `${label}: ${invalid.validationMessage || "invalid value"}`;
    }
    return "";
  };

  // This listener is deliberately installed after all pre-existing deferred Strategy Builder assets.
  // It therefore observes the final defaultPrevented state after composer, exit-sweep and entry-sweep
  // validation have had a chance to build their hidden request fields or reject the run.
  setTimeout(() => {
    if (form.dataset.diagnosticSubmitWired === "1") return;
    form.dataset.diagnosticSubmitWired = "1";
    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented) {
        const reason = firstComposerError() || "A Strategy Builder validation rule cancelled the run.";
        showFailure(reason, "Nothing was sent to the backend. Correct the item above and press Run research again.");
        return;
      }

      // Take ownership of the final navigation so the submitted request is deterministic and
      // inspectable. All earlier submit handlers have already materialized expression/rule/exit
      // hidden inputs by this point.
      event.preventDefault();
      const data = new FormData(form);
      data.delete("load_only");
      data.set("execute_run", "1");
      data.set("run_attempt", `${Date.now()}`);
      const params = new URLSearchParams();
      for (const [key, value] of data.entries()) params.append(key, String(value));
      const destination = `/research/strategy?${params.toString()}`;
      const dock = document.getElementById("strategy-run-dock");
      const status = dock?.querySelector(".run-submit-status");
      if (status) status.textContent = "Request accepted — starting research…";
      window.location.assign(destination);
    }, false);
  }, 0);

  // If the backend parsed the request but rejected it, the normal renderer includes a .error box.
  // Surface that reason immediately rather than requiring the operator to search the page.
  const query = new URLSearchParams(window.location.search);
  const backendError = document.querySelector(".error");
  if (query.get("run_attempt") && backendError?.textContent?.trim()) {
    showFailure(
      backendError.textContent.trim().replace(/^Cannot run strategy:\s*/i, ""),
      "The request reached the backend, but SCOUT rejected the configuration before completing research."
    );
  }

  // A plain-text 500 cannot host this script, so the run-attempt marker also makes terminal requests
  // identifiable. Normal handled configuration failures remain HTML and are shown above.
})();
"""


def configure_research_station_runtime() -> None:
    """Install all prior workflow repairs plus deterministic run diagnostics."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v3.configure_research_station_runtime()
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    asset = cast(str, getattr(_console, asset_name))
    if "research-run-diagnostic-modal" not in asset:
        setattr(_console, asset_name, asset + "\n" + _RESEARCH_STATION_V4_JS)
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
