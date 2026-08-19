# ruff: noqa: E501
"""Browser stability shim that keeps recovered fixed metrics on their catalog threshold contract."""

from __future__ import annotations

from typing import cast

from trade_scout.app import research_workbench_console as _console

_CONFIGURED = False

_THRESHOLD_CONTRACT_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;

  const repair = () => {
    const catalogNode = document.getElementById("strategy-catalog-json");
    const rules = document.getElementById("rule-rows");
    if (!catalogNode || !rules) return;
    let catalog;
    try { catalog = JSON.parse(catalogNode.textContent || "[]"); } catch (_) { return; }
    const byFeature = new Map(catalog.map((item) => [item.feature_name, item]));
    rules.querySelectorAll(".rule-row").forEach((row) => {
      if (row.querySelector(".rule-indicator")?.value !== "legacy_fixed") return;
      const feature = row.querySelector(".rule-metric")?.value;
      const meta = byFeature.get(feature);
      if (!meta) return;
      const value = row.querySelector(".rule-value");
      const slider = row.querySelector(".rule-slider");
      if (!value || !slider) return;
      for (const node of [value, slider]) {
        node.min = String(meta.min_value);
        node.max = String(meta.max_value);
        node.step = String(meta.step);
      }
    });
  };

  const install = () => {
    repair();
    const rules = document.getElementById("rule-rows");
    if (!rules || rules.dataset.thresholdContractObserver === "1") return;
    rules.dataset.thresholdContractObserver = "1";
    new MutationObserver(repair).observe(rules, { childList: true, subtree: true });
    rules.addEventListener("change", () => window.setTimeout(repair, 0), true);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
"""


def configure_threshold_contract_ui() -> None:
    """Append the fixed-metric threshold repair once to the Research Station asset."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    namespace = vars(_console)
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    asset = cast(str, namespace[asset_name])
    if "thresholdContractObserver" not in asset:
        namespace[asset_name] = asset + "\n" + _THRESHOLD_CONTRACT_JS
    _CONFIGURED = True


__all__ = ["configure_threshold_contract_ui"]
