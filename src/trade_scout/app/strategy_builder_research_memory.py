"""Small presentation asset linking saved Strategy Builder runs to durable research memory."""

STRATEGY_BUILDER_RESEARCH_MEMORY_JS = r"""
(() => {
  "use strict";

  const installPrintRules = () => {
    if (document.getElementById("ts-research-memory-print-style")) return;
    const style = document.createElement("style");
    style.id = "ts-research-memory-print-style";
    style.textContent = `
      @media print {
        #experiment-record,
        #experiment-record table,
        #experiment-record tr {
          break-inside: avoid-page !important;
          page-break-inside: avoid !important;
        }
        #experiment-record .memory-actions { display: none !important; }
      }
    `;
    document.head.appendChild(style);
  };

  const experimentId = (card) => {
    const rows = Array.from(card.querySelectorAll("tr"));
    for (const row of rows) {
      const heading = row.querySelector("th");
      const code = row.querySelector("td code");
      if (heading && code && heading.textContent.trim() === "Experiment ID") {
        return code.textContent.trim();
      }
    }
    return "";
  };

  const addActions = (card, id) => {
    if (!id || card.querySelector(".memory-actions")) return;
    const actions = document.createElement("div");
    actions.className = "memory-actions";
    actions.style.display = "flex";
    actions.style.flexWrap = "wrap";
    actions.style.gap = "10px";
    actions.style.marginTop = "12px";

    const library = document.createElement("a");
    library.href = `/research/experiments?experiment=${encodeURIComponent(id)}`;
    library.textContent = "Open saved experiment";
    library.style.fontWeight = "700";

    const brain = document.createElement("a");
    brain.href = `/research/brains?experiment=${encodeURIComponent(id)}`;
    brain.textContent = "Add this run to a research brain";
    brain.style.fontWeight = "700";

    actions.append(library, brain);
    card.appendChild(actions);
  };

  const enhance = () => {
    installPrintRules();
    const card = document.getElementById("experiment-record");
    if (!card) return;
    addActions(card, experimentId(card));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhance, { once: true });
  } else {
    enhance();
  }
})();
"""

__all__ = ["STRATEGY_BUILDER_RESEARCH_MEMORY_JS"]
