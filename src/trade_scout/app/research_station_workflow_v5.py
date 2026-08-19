# ruff: noqa: E501
"""Research Station run repair with observable browser validation.

The persistent Run dock is created after the research-memory asset starts executing, so Run installation
must wait for that dock. In addition, browser constraint validation happens before a form ``submit``
event. A native submit button can therefore remain stuck at "Validating configuration..." when an
invalid control suppresses submission entirely. This layer preserves the suite/Brain integration chain,
installs only after the persistent dock exists, validates explicitly, and then enters the normal submit
pipeline with ``requestSubmit()``.
"""

from __future__ import annotations

from typing import cast

from trade_scout.app import research_station_workflow_v4 as _v4
from trade_scout.app import research_workbench_console as _console

_CONFIGURED = False

_RESEARCH_STATION_V5_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const form = document.getElementById("strategy-form");
  if (!form) return;

  const ensureModal = () => {
    let root = document.getElementById("research-run-diagnostic-modal");
    if (root) return root;
    const style = document.createElement("style");
    style.id = "research-run-diagnostic-style-v5";
    style.textContent = `
      #research-run-diagnostic-modal[hidden] { display:none !important; }
      #research-run-diagnostic-modal { position:fixed; inset:0; z-index:6000; display:grid; place-items:center; padding:22px; background:rgba(3,6,10,.78); }
      #research-run-diagnostic-modal .diagnostic-panel { width:min(720px,96vw); max-height:min(78vh,720px); overflow:auto; border:1px solid #6d5b24; border-radius:14px; background:#121720; box-shadow:0 24px 70px rgba(0,0,0,.55); padding:18px; }
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
    return root;
  };

  const modal = ensureModal();
  const showFailure = (reason, detail = "") => {
    modal.querySelector(".diagnostic-reason").textContent = reason || "The run was cancelled before reaching the backend.";
    modal.querySelector(".diagnostic-detail").textContent = detail;
    modal.hidden = false;
  };

  const failureReason = () => {
    const composer = document.getElementById("composer-error");
    if (composer && !composer.hidden && composer.textContent.trim()) return composer.textContent.trim();
    const sweep = document.getElementById("sweep-preview");
    if (sweep?.textContent?.trim().startsWith("Fix ")) return sweep.textContent.trim();
    for (const node of form.elements) {
      if (typeof node.checkValidity === "function" && !node.checkValidity()) {
        const label = node.closest?.("label")?.textContent?.trim() || node.getAttribute?.("name") || "A form field";
        return `${label}: ${node.validationMessage || "invalid value"}`;
      }
    }
    return "A Strategy Builder validation rule cancelled the run before it reached the backend.";
  };

  let runtime = document.getElementById("research-run-runtime");
  if (!runtime) {
    runtime = document.createElement("div");
    runtime.id = "research-run-runtime";
    runtime.style.cssText = "font-size:11px;color:#7fc8ff;margin-left:auto;white-space:nowrap";
    runtime.textContent = "Run path: native-v5-validation-fix";
  }

  const installNativeRun = () => {
    const dock = document.getElementById("strategy-run-dock");
    const oldRun = dock?.querySelector("button.primary");
    if (!dock || !oldRun) return false;
    if (oldRun.dataset.nativeRun === "1") return true;

    const run = oldRun.cloneNode(true);
    run.type = "button";
    run.dataset.nativeRun = "1";
    run.disabled = false;
    run.textContent = "Run research";
    oldRun.replaceWith(run);

    let status = dock.querySelector(".run-submit-status");
    if (!status) {
      status = document.createElement("div");
      status.className = "run-submit-status";
      status.style.cssText = "font-size:12px;color:#98a6b8;min-width:150px;text-align:right";
      dock.insertBefore(status, run);
    }
    if (!runtime.isConnected) dock.insertBefore(runtime, status);

    run.addEventListener("click", (event) => {
      event.preventDefault();
      status.textContent = "Validating configuration…";
      if (!form.reportValidity()) {
        status.textContent = "Research blocked by invalid browser input.";
        showFailure(
          failureReason(),
          "Browser validation blocked the request before a submit event could occur. Correct the highlighted field and press Run research again. Nothing was sent to the backend."
        );
        return;
      }
      try {
        form.requestSubmit();
      } catch (error) {
        status.textContent = "Research could not be submitted.";
        showFailure(
          `Could not submit the research form: ${error instanceof Error ? error.message : String(error)}`,
          "The Run action was received and browser validation passed, but requestSubmit() failed before backend execution."
        );
      }
    });
    return true;
  };

  // The persistent run dock is created by the earlier v2 layer on DOMContentLoaded. Wait until the
  // known-good dock exists, then replace only its Run button. No document-level click interception
  // and no suite/Brain control mutation is used here.
  const scheduleNativeRunInstall = () => {
    let attempts = 0;
    const attempt = () => {
      if (installNativeRun()) return;
      attempts += 1;
      if (attempts < 80) window.setTimeout(attempt, 25);
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => window.setTimeout(attempt, 0), { once: true });
    } else {
      window.setTimeout(attempt, 0);
    }
  };
  scheduleNativeRunInstall();

  // Capture phase runs before the existing composer/sweep submit handlers. Once explicit browser
  // validation passes, requestSubmit() enters this normal pipeline. We then inspect the same Event
  // after later handlers have had the opportunity to preventDefault().
  form.addEventListener("submit", (event) => {
    let marker = form.querySelector('input[name="execute_run"]');
    if (!marker) {
      marker = document.createElement("input");
      marker.type = "hidden";
      marker.name = "execute_run";
      form.append(marker);
    }
    marker.value = "1";

    const dock = document.getElementById("strategy-run-dock");
    const status = dock?.querySelector(".run-submit-status");
    if (status) status.textContent = "Submitting research…";

    window.setTimeout(() => {
      if (!event.defaultPrevented) return;
      if (status) status.textContent = "Research was blocked before backend execution.";
      showFailure(
        failureReason(),
        "The browser received your Run command, but a client-side Strategy Builder validation rule stopped submission. Nothing was sent to the research backend."
      );
    }, 0);
  }, true);

  const query = new URLSearchParams(window.location.search);
  const backendError = document.querySelector(".error");
  if (query.get("execute_run") === "1" && backendError?.textContent?.trim()) {
    showFailure(
      backendError.textContent.trim().replace(/^Cannot run strategy:\s*/i, ""),
      "The request reached the backend, but SCOUT rejected the resolved configuration before completing research."
    );
  }
})();
"""


def configure_research_station_runtime() -> None:
    """Install prior workflow repairs and attach observable Run after the persistent dock exists."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v4.configure_research_station_runtime()
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    asset = cast(str, namespace[asset_name])
    if "Run path: native-v5-validation-fix" not in asset:
        namespace[asset_name] = asset + "\n" + _RESEARCH_STATION_V5_JS
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
