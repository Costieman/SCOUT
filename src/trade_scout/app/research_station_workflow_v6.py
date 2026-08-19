# ruff: noqa: E501
"""Sixth-pass Research Station run repair for late-created run controls.

The v5 native-submit logic assumed the persistent run dock already existed when the research-memory
asset executed. In practice that dock can be created later by another Strategy Builder asset, leaving
v5 loaded on the server but not installed in the browser. This layer makes installation lifecycle-safe:
it exposes an independent runtime badge immediately, observes late DOM creation, and captures clicks on
the run dock so a click always becomes a real form submission attempt or an explicit visible failure.
"""

from __future__ import annotations

from typing import cast

from trade_scout.app import research_station_workflow_v5 as _v5
from trade_scout.app import research_workbench_console as _console

_CONFIGURED = False

_RESEARCH_STATION_V6_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const form = document.getElementById("strategy-form");
  if (!form) return;

  const ensureGlobalBadge = () => {
    let badge = document.getElementById("research-run-runtime-v6");
    if (badge) return badge;
    badge = document.createElement("div");
    badge.id = "research-run-runtime-v6";
    badge.textContent = "Run path: lifecycle-v6";
    badge.style.cssText = "position:fixed;right:14px;bottom:72px;z-index:6500;padding:5px 8px;border:1px solid #315d7a;border-radius:7px;background:#0d1822;color:#8ed2ff;font:11px/1.2 monospace;box-shadow:0 4px 18px rgba(0,0,0,.35)";
    document.body.append(badge);
    return badge;
  };

  const ensureModal = () => {
    let root = document.getElementById("research-run-diagnostic-modal");
    if (root) return root;
    root = document.createElement("div");
    root.id = "research-run-diagnostic-modal";
    root.hidden = true;
    root.style.cssText = "position:fixed;inset:0;z-index:7000;display:grid;place-items:center;padding:22px;background:rgba(3,6,10,.78)";
    root.innerHTML = `<div style="width:min(720px,96vw);max-height:78vh;overflow:auto;border:1px solid #6d5b24;border-radius:14px;background:#121720;box-shadow:0 24px 70px rgba(0,0,0,.55);padding:18px">
      <h2>Research did not start</h2>
      <div data-reason style="padding:12px;border-left:3px solid #ef7b7b;background:#221315;color:#f4c4c4;white-space:pre-wrap"></div>
      <div data-detail style="color:#aab5c3;margin-top:10px;white-space:pre-wrap;font-size:12px"></div>
      <div style="display:flex;justify-content:flex-end;margin-top:14px"><button type="button" data-close>Close</button></div>
    </div>`;
    document.body.append(root);
    root.querySelector("[data-close]")?.addEventListener("click", () => { root.hidden = true; });
    return root;
  };

  const modal = ensureModal();
  const showFailure = (reason, detail) => {
    modal.querySelector("[data-reason]").textContent = reason || "The run was cancelled before reaching the backend.";
    modal.querySelector("[data-detail]").textContent = detail || "";
    modal.hidden = false;
  };

  const invalidReason = () => {
    for (const node of form.elements) {
      if (typeof node.checkValidity === "function" && !node.checkValidity()) {
        const label = node.closest?.("label")?.textContent?.trim() || node.getAttribute?.("name") || "A form field";
        return `${label}: ${node.validationMessage || "invalid value"}`;
      }
    }
    return "";
  };

  const ensureExecuteMarker = () => {
    let marker = form.querySelector('input[name="execute_run"]');
    if (!marker) {
      marker = document.createElement("input");
      marker.type = "hidden";
      marker.name = "execute_run";
      form.append(marker);
    }
    marker.value = "1";
    form.querySelectorAll('input[name="load_only"]').forEach((node) => node.remove());
  };

  const installDock = () => {
    const dock = document.getElementById("strategy-run-dock");
    if (!dock) return false;
    const run = dock.querySelector("button.primary");
    if (!run) return false;
    run.dataset.lifecycleRun = "1";
    run.type = "button";
    run.disabled = false;
    run.textContent = "Run research";
    let status = dock.querySelector(".run-submit-status-v6");
    if (!status) {
      status = document.createElement("div");
      status.className = "run-submit-status-v6";
      status.style.cssText = "font-size:12px;color:#98a6b8;min-width:180px;text-align:right";
      dock.insertBefore(status, run);
    }
    return true;
  };

  ensureGlobalBadge();
  installDock();

  const observer = new MutationObserver(() => installDock());
  observer.observe(document.body, {childList:true, subtree:true});

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest("#strategy-run-dock button.primary") : null;
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    const dock = document.getElementById("strategy-run-dock");
    const status = dock?.querySelector(".run-submit-status-v6");
    if (status) status.textContent = "Validating configuration…";

    const invalid = invalidReason();
    if (invalid) {
      if (status) status.textContent = "Research blocked by invalid input.";
      showFailure(invalid, "The Run button was received, but browser validation rejected a field before submission.");
      return;
    }

    ensureExecuteMarker();
    if (status) status.textContent = "Submitting research…";

    // requestSubmit triggers the existing Strategy Builder submit handlers so they can compile the
    // current entry rules, exits, and sweep state. If any handler cancels submission, the v5/v6
    // submit diagnostics surface that cancellation instead of failing silently.
    form.requestSubmit();

    window.setTimeout(() => {
      if (document.visibilityState === "visible" && status?.textContent === "Submitting research…") {
        const composer = document.getElementById("composer-error");
        const reason = composer && !composer.hidden && composer.textContent.trim()
          ? composer.textContent.trim()
          : "The form remained on this page after the Run command. A client-side handler likely cancelled submission.";
        status.textContent = "Research did not leave the browser.";
        showFailure(reason, "No backend navigation was observed after requestSubmit(). Check the visible reason above; the server log should contain no execute_run request in this case.");
      }
    }, 250);
  }, true);
})();
"""


def configure_research_station_runtime() -> None:
    """Install v5 and then the lifecycle-safe v6 run integration."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v5.configure_research_station_runtime()
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    asset = cast(str, namespace[asset_name])
    if "Run path: lifecycle-v6" not in asset:
        namespace[asset_name] = asset + "\n" + _RESEARCH_STATION_V6_JS
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
