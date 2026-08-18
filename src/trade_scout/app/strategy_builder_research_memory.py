"""Presentation asset linking Strategy Builder runs to durable research-brain session memory."""

STRATEGY_BUILDER_RESEARCH_MEMORY_JS = r"""
(() => {
  "use strict";

  const ACTIVE_BRAIN_KEY = "trade-scout:research-brain:active";
  const brainStateKey = (brainId) => `trade-scout:research-brain:${brainId}:session`;

  const readState = (brainId) => {
    if (!brainId) return null;
    try {
      return JSON.parse(localStorage.getItem(brainStateKey(brainId)) || "null");
    } catch (_) {
      return null;
    }
  };

  const writeState = (brainId, patch) => {
    if (!brainId) return;
    const prior = readState(brainId) || {};
    localStorage.setItem(
      brainStateKey(brainId),
      JSON.stringify({ ...prior, ...patch, updated_at: new Date().toISOString() })
    );
  };

  const cleanStrategyUrl = () => {
    const url = new URL(window.location.href);
    url.hash = "";
    url.searchParams.delete("brain");
    return url.pathname + (url.search || "");
  };

  const configurationFingerprint = () => {
    const url = new URL(window.location.href);
    const ignored = new Set(["experiment", "brain", "message"]);
    const pairs = [];
    for (const [key, value] of url.searchParams.entries()) {
      if (!ignored.has(key)) pairs.push([key, value]);
    }
    pairs.sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]));
    return JSON.stringify(pairs);
  };

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
        #experiment-record .memory-actions,
        #research-brain-session-card { display: none !important; }
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

  const activeBrainId = () => localStorage.getItem(ACTIVE_BRAIN_KEY) || "";

  const rememberCurrentWork = (experiment = "") => {
    const brainId = activeBrainId();
    if (!brainId) return;
    const patch = {
      last_url: cleanStrategyUrl(),
      last_fingerprint: configurationFingerprint(),
    };
    if (experiment) {
      patch.last_experiment_id = experiment;
      patch.last_run_fingerprint = configurationFingerprint();
    }
    writeState(brainId, patch);
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
    const selectedBrain = activeBrainId();
    const params = new URLSearchParams({ experiment: id });
    if (selectedBrain) params.set("brain", selectedBrain);
    brain.href = `/research/brains?${params.toString()}`;
    brain.textContent = selectedBrain
      ? "Add this run to the selected research brain"
      : "Add this run to a research brain";
    brain.style.fontWeight = "700";
    brain.addEventListener("click", () => rememberCurrentWork(id));

    actions.append(library, brain);
    card.appendChild(actions);
  };

  const fetchBrainOptions = async () => {
    try {
      const response = await fetch("/research/brains", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return [];
      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const byId = new Map();

      // Prefer the explicit assignment selector when present.
      for (const option of doc.querySelectorAll('select[name="brain_id"] option')) {
        const id = option.value.trim();
        const name = option.textContent.trim();
        if (id && name) byId.set(id, { id, name });
      }

      // Fall back to the brain inventory links. This is intentionally redundant because
      // the Strategy Builder must remain connected even if the assignment form changes.
      for (const link of doc.querySelectorAll('a[href^="/research/brains?brain="]')) {
        const href = link.getAttribute("href") || "";
        const url = new URL(href, window.location.origin);
        const id = (url.searchParams.get("brain") || "").trim();
        const name = link.querySelector("strong")?.textContent?.trim() || link.textContent.trim();
        if (id && name && !byId.has(id)) byId.set(id, { id, name });
      }
      return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
    } catch (_) {
      return [];
    }
  };

  const showDuplicateNotice = (host, state) => {
    let notice = host.querySelector(".brain-duplicate-notice");
    if (!notice) {
      notice = document.createElement("div");
      notice.className = "section-note brain-duplicate-notice";
      notice.style.marginTop = "10px";
      host.appendChild(notice);
    }
    if (!state?.last_run_fingerprint || state.last_run_fingerprint !== configurationFingerprint()) {
      notice.hidden = true;
      return;
    }
    notice.hidden = false;
    const experiment = state.last_experiment_id || "a previous run";
    notice.innerHTML = `<strong>This exact configuration has already been run in this brain.</strong> ${experiment === "a previous run" ? experiment : `<a href="/research/experiments?experiment=${encodeURIComponent(experiment)}">Open ${experiment}</a>`}. Change one declared parameter if you want new evidence; for example, move one neighboring stop/target value or test one unresolved dimension rather than changing several settings at once.`;
  };

  const installBrainSessionCard = async () => {
    if (document.getElementById("research-brain-session-card")) return;
    const form = document.getElementById("strategy-form");
    if (!form) return;
    const firstCard = form.querySelector(":scope > .card");
    if (!firstCard) return;

    const card = document.createElement("div");
    card.id = "research-brain-session-card";
    card.className = "card";
    card.innerHTML = `
      <h2>Research brain — working session</h2>
      <div class="section-note"><strong>Choose the research thread before you iterate.</strong> SCOUT remembers the most recent Strategy Builder configuration for that brain so you can change one thing at a time without reconstructing the previous run from memory.</div>
      <div class="top-grid">
        <label>Research brain<select id="research-brain-session-select"><option value="">No brain selected — standalone research</option></select></label>
        <div style="align-self:end;display:flex;gap:8px;flex-wrap:wrap"><a id="research-brain-open" class="run-link" href="/research/brains" style="padding:9px 10px;border:1px solid #6d5b24;border-radius:8px">Open brain</a><button id="research-brain-resume" type="button" hidden>Resume last session</button></div>
      </div>
      <div id="research-brain-session-status" class="subtle" style="margin-top:8px">Loading research brains…</div>`;
    firstCard.insertAdjacentElement("beforebegin", card);

    const select = card.querySelector("#research-brain-session-select");
    const status = card.querySelector("#research-brain-session-status");
    const open = card.querySelector("#research-brain-open");
    const resume = card.querySelector("#research-brain-resume");
    const options = await fetchBrainOptions();
    for (const item of options) select.append(new Option(item.name, item.id));

    const queryBrain = (new URL(window.location.href).searchParams.get("brain") || "").trim();
    const priorActive = activeBrainId();
    const requestedBrain = queryBrain || priorActive;
    if (requestedBrain && options.some((item) => item.id === requestedBrain)) {
      select.value = requestedBrain;
      localStorage.setItem(ACTIVE_BRAIN_KEY, requestedBrain);
    }

    const refresh = () => {
      const brainId = select.value;
      const state = readState(brainId);
      if (!brainId) {
        open.href = "/research/brains";
        resume.hidden = true;
        status.textContent = options.length
          ? "Standalone research. Select a brain to preserve a working-session trail."
          : "No research brains were discovered. Open Research Brains to create one, then return here.";
        showDuplicateNotice(card, null);
        return;
      }
      open.href = `/research/brains?brain=${encodeURIComponent(brainId)}`;
      resume.hidden = !state?.last_url;
      status.textContent = state?.last_url
        ? `Last working configuration remembered ${state.updated_at ? new Date(state.updated_at).toLocaleString() : "for this brain"}. Selecting Resume restores it exactly.`
        : "No prior Strategy Builder session has been remembered for this brain yet. Your next run will become its starting point.";
      showDuplicateNotice(card, state);
    };

    select.addEventListener("change", () => {
      const brainId = select.value;
      if (brainId) localStorage.setItem(ACTIVE_BRAIN_KEY, brainId);
      else localStorage.removeItem(ACTIVE_BRAIN_KEY);
      refresh();
      const state = readState(brainId);
      if (brainId && state?.last_url && state.last_url !== cleanStrategyUrl()) {
        status.innerHTML = `<strong>Previous session found.</strong> Use “Resume last session” to restore the exact prior parameters before changing the next variable.`;
      }
    });

    resume.addEventListener("click", () => {
      const state = readState(select.value);
      if (state?.last_url) {
        const url = new URL(state.last_url, window.location.origin);
        url.searchParams.set("brain", select.value);
        window.location.assign(url.pathname + url.search);
      }
    });

    form.addEventListener("submit", () => {
      const brainId = select.value;
      if (!brainId) return;
      localStorage.setItem(ACTIVE_BRAIN_KEY, brainId);
      writeState(brainId, { pending_run: true });
    });

    refresh();
  };

  const enhance = () => {
    installPrintRules();
    installBrainSessionCard();
    const card = document.getElementById("experiment-record");
    if (!card) return;
    const id = experimentId(card);
    rememberCurrentWork(id);
    addActions(card, id);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhance, { once: true });
  } else {
    enhance();
  }
})();
"""

__all__ = ["STRATEGY_BUILDER_RESEARCH_MEMORY_JS"]
