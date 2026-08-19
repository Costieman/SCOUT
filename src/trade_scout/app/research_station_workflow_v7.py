# ruff: noqa: E501
"""Research Station validation diagnostics that identify and focus invalid controls.

This layer leaves the v5 Run, Strategy Suite, and Research Brain behavior unchanged. It improves both
native browser validation feedback and custom Strategy Builder validator feedback so a cancelled run
always tells the operator what failed and where to fix it.
"""

from __future__ import annotations

from typing import cast

from trade_scout.app import research_station_workflow_v5 as _v5
from trade_scout.app import research_workbench_console as _console

_CONFIGURED = False

_RESEARCH_STATION_V7_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const form = document.getElementById("strategy-form");
  if (!form) return;

  const cleanText = (value) => String(value || "").replace(/\s+/g, " ").replace(/\s*\?\s*$/g, "").trim();

  const labelText = (node) => {
    const label = node.closest?.("label");
    if (!label) return "";
    const clone = label.cloneNode(true);
    clone.querySelectorAll("input,select,textarea,button,option,.help-popover,.help-tooltip").forEach((item) => item.remove());
    return cleanText(clone.textContent);
  };

  const sectionText = (node) => {
    const card = node.closest?.(".card");
    const heading = card?.querySelector?.("h2,h3");
    return cleanText(heading?.textContent);
  };

  const fieldName = (node) => {
    const label = labelText(node);
    if (label) return label;
    const aria = cleanText(node.getAttribute?.("aria-label"));
    if (aria) return aria;
    const name = cleanText(node.getAttribute?.("name"));
    if (name) return name.replaceAll("_", " ");
    const classes = [...(node.classList || [])];
    const known = [
      ["rule-value", "Entry condition threshold"],
      ["param-period", "Indicator lookback / period"],
      ["param-deviations", "Bollinger Band standard deviations"],
      ["param-fast", "MACD fast EMA"],
      ["param-slow", "MACD slow EMA"],
      ["param-signal", "MACD signal EMA"],
      ["exit-stop-value", "Protective stop value"],
      ["exit-target-value", "Profit target value"],
      ["sweep-from", "Research variable — From"],
      ["sweep-to", "Research variable — To"],
      ["sweep-step", "Research variable — Step"],
    ];
    for (const [className, description] of known) {
      if (classes.includes(className)) return description;
    }
    return "Invalid research parameter";
  };

  const formatValue = (node) => {
    const value = String(node.value ?? "");
    return value === "" ? "(blank)" : value;
  };

  const expectedText = (node) => {
    const pieces = [];
    const min = node.getAttribute?.("min");
    const max = node.getAttribute?.("max");
    const step = node.getAttribute?.("step");
    if (min !== null && min !== "") pieces.push(`minimum ${min}`);
    if (max !== null && max !== "") pieces.push(`maximum ${max}`);
    if (step !== null && step !== "" && step !== "any") pieces.push(`step ${step}`);
    return pieces.length ? pieces.join(", ") : "Use a value accepted by this control.";
  };

  const clearHighlight = () => {
    form.querySelectorAll(".research-invalid-focus").forEach((node) => node.classList.remove("research-invalid-focus"));
    form.querySelectorAll(".research-invalid-focus-label").forEach((node) => node.classList.remove("research-invalid-focus-label"));
  };

  const ensureStyle = () => {
    if (document.getElementById("research-validation-focus-style")) return;
    const style = document.createElement("style");
    style.id = "research-validation-focus-style";
    style.textContent = `
      .research-invalid-focus { outline:3px solid #ef7b7b !important; outline-offset:3px !important; box-shadow:0 0 0 7px rgba(239,123,123,.16) !important; border-color:#ef7b7b !important; }
      .research-invalid-focus-label { color:#ffadad !important; }
    `;
    document.head.append(style);
  };
  ensureStyle();

  let lastInvalid = null;

  const focusInvalid = (node) => {
    if (!node) return;
    clearHighlight();
    node.classList.add("research-invalid-focus");
    node.closest?.("label")?.classList.add("research-invalid-focus-label");
    try { node.focus({ preventScroll: true }); } catch (_) { try { node.focus(); } catch (_) {} }
    window.setTimeout(() => node.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" }), 80);
  };

  const modalParts = () => {
    const modal = document.getElementById("research-run-diagnostic-modal");
    if (!modal || modal.hidden) return null;
    return {
      modal,
      reason: modal.querySelector(".diagnostic-reason"),
      detail: modal.querySelector(".diagnostic-detail"),
    };
  };

  const enhanceModal = (node) => {
    const parts = modalParts();
    if (!parts || !node) return;
    const field = fieldName(node);
    const section = sectionText(node);
    const browserReason = node.validationMessage || "Invalid value.";
    if (parts.reason) {
      parts.reason.textContent = `${section ? section + " → " : ""}${field}\nCurrent value: ${formatValue(node)}\nProblem: ${browserReason}\nExpected: ${expectedText(node)}`;
    }
    if (parts.detail) {
      parts.detail.textContent = "Close this message and SCOUT will take you to the invalid parameter, which is highlighted in red. Correct it, then press Run research again. Nothing was sent to the backend.";
    }
  };

  const customValidationSource = () => {
    const composer = document.getElementById("composer-error");
    const composerText = composer && !composer.hidden ? cleanText(composer.textContent) : "";
    if (composerText) return { source: "Strategy Builder", message: composerText, target: inferTarget(composerText) };

    const sweep = document.getElementById("sweep-preview");
    const sweepText = cleanText(sweep?.textContent);
    if (sweepText.startsWith("Fix entry sweep:") || sweepText.startsWith("Fix sweep:")) {
      return { source: "Research variable", message: sweepText, target: document.getElementById("sweep-from") || document.getElementById("sweep-variable") };
    }
    if (sweepText.includes("interactive safety limit") || sweepText.includes("temporarily capped")) {
      return { source: "Research variable", message: sweepText, target: document.getElementById("sweep-step") || document.getElementById("sweep-variable") };
    }
    return null;
  };

  function inferTarget(message) {
    const text = message.toLowerCase();
    if (text.includes("profit target")) return form.querySelector(".exit-target-value");
    if (text.includes("protective stop") || text.includes("stop value")) return form.querySelector(".exit-stop-value");
    if (text.includes("advanced expression")) return document.getElementById("advanced-expression");
    if (text.includes("entry condition") || text.includes("numeric condition")) return form.querySelector(".rule-value");
    if (text.includes("entry sweep")) return document.getElementById("sweep-from") || document.getElementById("sweep-variable");
    return null;
  }

  const enhanceCustomCancellation = () => {
    const parts = modalParts();
    if (!parts) return;
    const generic = cleanText(parts.reason?.textContent);
    if (!generic.includes("validation rule cancelled the run") && !generic.includes("cancelled before reaching the backend")) return;
    const diagnostic = customValidationSource();
    if (!diagnostic) {
      if (parts.reason) parts.reason.textContent = "A client-side validator cancelled this run, but it did not publish a diagnostic message. This is a SCOUT validation-path bug, not an actionable user error.";
      if (parts.detail) parts.detail.textContent = "Nothing was sent to the backend. Please report this exact popup; SCOUT should never ask you to guess which parameter failed.";
      return;
    }
    if (parts.reason) parts.reason.textContent = `${diagnostic.source} validation failed\n${diagnostic.message}`;
    if (parts.detail) parts.detail.textContent = diagnostic.target
      ? "Close this message and SCOUT will move to the most likely offending control and highlight it in red. Nothing was sent to the backend."
      : "Nothing was sent to the backend. The validator supplied the reason above, but did not identify a single editable control.";
    if (diagnostic.target) focusInvalid(diagnostic.target);
  };

  form.addEventListener("invalid", (event) => {
    const node = event.target;
    if (!(node instanceof HTMLElement)) return;
    if (!lastInvalid || lastInvalid.checkValidity?.()) lastInvalid = node;
    focusInvalid(node);
    window.setTimeout(() => enhanceModal(lastInvalid || node), 0);
  }, true);

  form.addEventListener("input", (event) => {
    const node = event.target;
    if (!(node instanceof HTMLElement)) return;
    if (node.classList.contains("research-invalid-focus") && node.checkValidity?.()) {
      node.classList.remove("research-invalid-focus");
      node.closest?.("label")?.classList.remove("research-invalid-focus-label");
      if (lastInvalid === node) lastInvalid = null;
    }
  }, true);

  document.addEventListener("click", (event) => {
    const run = event.target?.closest?.("#strategy-run-dock button.primary");
    if (!run) return;
    lastInvalid = null;
    window.setTimeout(() => {
      if (lastInvalid) enhanceModal(lastInvalid);
      else enhanceCustomCancellation();
    }, 30);
  }, true);
})();
"""


def configure_research_station_runtime() -> None:
    """Install v5 and append specific validation diagnostics without changing research behavior."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v5.configure_research_station_runtime()
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    asset = cast(str, namespace[asset_name])
    if "customValidationSource" not in asset:
        namespace[asset_name] = asset + "\n" + _RESEARCH_STATION_V7_JS
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
