# ruff: noqa: E501
"""Research Station validation diagnostics that identify and focus the invalid control.

This layer deliberately leaves the v5 Run, Strategy Suite, and Research Brain behavior unchanged. It
only improves browser-side validation feedback after v5 has identified an invalid form control.
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

  const enhanceModal = (node) => {
    const modal = document.getElementById("research-run-diagnostic-modal");
    if (!modal || modal.hidden || !node) return;
    const field = fieldName(node);
    const section = sectionText(node);
    const reason = modal.querySelector(".diagnostic-reason");
    const detail = modal.querySelector(".diagnostic-detail");
    const browserReason = node.validationMessage || "Invalid value.";
    if (reason) {
      reason.textContent = `${section ? section + " → " : ""}${field}\nCurrent value: ${formatValue(node)}\nProblem: ${browserReason}\nExpected: ${expectedText(node)}`;
    }
    if (detail) {
      detail.textContent = "Close this message and SCOUT will take you to the invalid parameter, which is highlighted in red. Correct it, then press Run research again. Nothing was sent to the backend.";
    }
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

  // If v5 has already opened the modal, improve it using the exact invalid control captured above.
  document.addEventListener("click", (event) => {
    const run = event.target?.closest?.("#strategy-run-dock button.primary");
    if (!run) return;
    lastInvalid = null;
    window.setTimeout(() => {
      if (lastInvalid) enhanceModal(lastInvalid);
    }, 10);
  }, true);
})();
"""


def configure_research_station_runtime() -> None:
    """Install v5 and append focused validation diagnostics without changing research behavior."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v5.configure_research_station_runtime()
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    asset = cast(str, namespace[asset_name])
    if "research-validation-focus-style" not in asset:
        namespace[asset_name] = asset + "\n" + _RESEARCH_STATION_V7_JS
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
