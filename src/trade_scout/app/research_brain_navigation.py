# ruff: noqa: E501
"""Presentation-only navigation joining Research Brains back to Strategy Builder."""

RESEARCH_BRAIN_NAVIGATION_JS = r"""
(() => {
  "use strict";
  if (window.location.pathname !== "/research/brains") return;

  const ACTIVE_BRAIN_KEY = "trade-scout:research-brain:active";

  const brainIdFromHref = (href) => {
    try {
      const url = new URL(href, window.location.origin);
      return (url.searchParams.get("brain") || "").trim();
    } catch (_) {
      return "";
    }
  };

  const strategyHref = (brainId) => `/research/strategy?brain=${encodeURIComponent(brainId)}`;

  const addContinueLink = (host, brainId, label = "Continue research in Strategy Builder") => {
    if (!host || !brainId || host.querySelector('.brain-continue-research')) return;
    const link = document.createElement("a");
    link.className = "button brain-continue-research";
    link.href = strategyHref(brainId);
    link.textContent = label;
    link.style.marginTop = "8px";
    link.style.display = "inline-flex";
    link.addEventListener("click", () => localStorage.setItem(ACTIVE_BRAIN_KEY, brainId));
    host.appendChild(link);
  };

  for (const link of document.querySelectorAll('a[href^="/research/brains?brain="]')) {
    const brainId = brainIdFromHref(link.getAttribute("href") || "");
    const cell = link.closest("td");
    if (brainId && cell) addContinueLink(cell, brainId, "Research from this brain");
  }

  const detail = document.getElementById("brain-detail");
  if (detail) {
    const currentBrain = (new URL(window.location.href).searchParams.get("brain") || "").trim();
    if (currentBrain) {
      const heading = detail.querySelector("h2");
      const host = document.createElement("div");
      host.style.display = "flex";
      host.style.gap = "8px";
      host.style.flexWrap = "wrap";
      host.style.marginBottom = "12px";
      heading?.insertAdjacentElement("afterend", host);
      addContinueLink(host, currentBrain);
    }
  }

  const preselected = (new URL(window.location.href).searchParams.get("brain") || "").trim();
  if (preselected) {
    const addSelect = document.querySelector('form[action="/research/brains"] select[name="brain_id"]');
    if (addSelect && [...addSelect.options].some((option) => option.value === preselected)) {
      addSelect.value = preselected;
    }
  }
})();
"""

__all__ = ["RESEARCH_BRAIN_NAVIGATION_JS"]
