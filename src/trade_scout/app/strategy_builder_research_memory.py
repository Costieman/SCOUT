# ruff: noqa: E501
"""Presentation asset joining Strategy Builder, strategy suites, and Research Brain sessions."""

from __future__ import annotations

import json

from trade_scout.app.strategy_suite_registry import built_in_strategy_suites
from trade_scout.app.strategy_suite_workflow import built_in_suite_launch_plans


def _suite_payload() -> str:
    plans = {item.suite_id: item for item in built_in_suite_launch_plans()}
    payload = []
    for suite in built_in_strategy_suites():
        plan = plans[suite.suite_id]
        payload.append(
            {
                "id": suite.suite_id,
                "name": suite.name,
                "family": suite.family,
                "evidence": suite.evidence_class.value,
                "timeframe": suite.canonical_timeframe,
                "description": suite.description,
                "recipe": list(suite.canonical_recipe),
                "axes": list(suite.parameter_axes),
                "status": plan.launch_status.value,
                "parameters": dict(plan.builder_parameters),
                "unresolved": list(plan.unresolved_capabilities),
                "note": plan.note,
            }
        )
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


_SUITE_JSON = _suite_payload()

STRATEGY_BUILDER_RESEARCH_MEMORY_JS = r"""
(() => {
  "use strict";

  const ACTIVE_BRAIN_KEY = "trade-scout:research-brain:active";
  const brainStateKey = (brainId) => `trade-scout:research-brain:${brainId}:session`;
  const SUITES = __SUITE_JSON__;

  const readState = (brainId) => {
    if (!brainId) return null;
    try { return JSON.parse(localStorage.getItem(brainStateKey(brainId)) || "null"); }
    catch (_) { return null; }
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

  const installPrintRules = () => {
    if (document.getElementById("ts-research-memory-print-style")) return;
    const style = document.createElement("style");
    style.id = "ts-research-memory-print-style";
    style.textContent = `@media print {
      #experiment-record,
      #experiment-record table,
      #experiment-record tr {
        break-inside: avoid-page !important;
        page-break-inside: avoid !important;
      }
      #experiment-record .memory-actions,
      #research-brain-session-card,
      #strategy-suite-card,
      #controlled-iteration-card { display:none !important; }
    }`;
    document.head.appendChild(style);
  };

  const experimentId = (card) => {
    for (const row of card.querySelectorAll("tr")) {
      const heading = row.querySelector("th");
      const code = row.querySelector("td code");
      if (heading && code && heading.textContent.trim() === "Experiment ID") return code.textContent.trim();
    }
    return "";
  };

  const addActions = (card, id) => {
    if (!id || card.querySelector(".memory-actions")) return;
    const actions = document.createElement("div");
    actions.className = "memory-actions";
    actions.style.cssText = "display:flex;flex-wrap:wrap;gap:10px;margin-top:12px";
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
      const doc = new DOMParser().parseFromString(await response.text(), "text/html");
      const byId = new Map();
      for (const option of doc.querySelectorAll('select[name="brain_id"] option')) {
        const id = option.value.trim();
        const name = option.textContent.trim();
        if (id && name) byId.set(id, { id, name });
      }
      for (const link of doc.querySelectorAll('a[href^="/research/brains?brain="]')) {
        const url = new URL(link.getAttribute("href") || "", window.location.origin);
        const id = (url.searchParams.get("brain") || "").trim();
        const name = link.querySelector("strong")?.textContent?.trim() || link.textContent.trim();
        if (id && name && !byId.has(id)) byId.set(id, { id, name });
      }
      return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
    } catch (_) { return []; }
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
    card.innerHTML = `<h2>Research brain — working session</h2>
      <div class="section-note"><strong>Choose the research thread before you iterate.</strong> SCOUT remembers the most recent Strategy Builder configuration for that brain so you can change one thing at a time without reconstructing the previous run from memory.</div>
      <div class="top-grid"><label>Research brain<select id="research-brain-session-select"><option value="">No brain selected — standalone research</option></select></label>
      <div style="align-self:end;display:flex;gap:8px;flex-wrap:wrap"><a id="research-brain-open" class="run-link" href="/research/brains" style="padding:9px 10px;border:1px solid #6d5b24;border-radius:8px">Open brain</a><button id="research-brain-resume" type="button" hidden>Resume last session</button></div></div>
      <div id="research-brain-session-status" class="subtle" style="margin-top:8px">Loading research brains…</div>`;
    firstCard.insertAdjacentElement("beforebegin", card);
    const select = card.querySelector("#research-brain-session-select");
    const status = card.querySelector("#research-brain-session-status");
    const open = card.querySelector("#research-brain-open");
    const resume = card.querySelector("#research-brain-resume");
    const options = await fetchBrainOptions();
    for (const item of options) select.append(new Option(item.name, item.id));
    const queryBrain = (new URL(window.location.href).searchParams.get("brain") || "").trim();
    const requestedBrain = queryBrain || activeBrainId();
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
        status.textContent = options.length ? "Standalone research. Select a brain to preserve a working-session trail." : "No research brains were discovered. Open Research Brains to create one, then return here.";
        showDuplicateNotice(card, null);
        return;
      }
      open.href = `/research/brains?brain=${encodeURIComponent(brainId)}`;
      resume.hidden = !state?.last_url;
      status.textContent = state?.last_url ? "Previous working configuration available. Resume it before changing the next variable." : "Your next run will become this brain's starting point.";
      showDuplicateNotice(card, state);
    };
    select.addEventListener("change", () => {
      if (select.value) localStorage.setItem(ACTIVE_BRAIN_KEY, select.value);
      else localStorage.removeItem(ACTIVE_BRAIN_KEY);
      refresh();
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
      if (!select.value) return;
      localStorage.setItem(ACTIVE_BRAIN_KEY, select.value);
      writeState(select.value, { pending_run: true });
    });
    refresh();
  };

  const suiteById = (id) => SUITES.find((item) => item.id === id) || null;

  const suiteLaunchUrl = (suite) => {
    const url = new URL("/research/strategy", window.location.origin);
    for (const [key, value] of Object.entries(suite.parameters || {})) url.searchParams.set(key, value);
    url.searchParams.set("suite", suite.id);
    const brain = (new URL(window.location.href).searchParams.get("brain") || activeBrainId()).trim();
    if (brain) url.searchParams.set("brain", brain);
    return url.pathname + url.search;
  };

  const installSuiteCard = () => {
    if (document.getElementById("strategy-suite-card")) return;
    const form = document.getElementById("strategy-form");
    if (!form) return;
    const anchor = document.getElementById("research-brain-session-card") || form.querySelector(":scope > .card");
    const card = document.createElement("div");
    card.id = "strategy-suite-card";
    card.className = "card";
    card.innerHTML = `<h2>Strategy suite</h2>
      <div class="section-note"><strong>Start from a documented hypothesis, then edit it.</strong> Suites are research presets, not endorsed trades. READY suites can populate the current builder; PARTIAL and BLOCKED suites remain visible without pretending missing logic exists.</div>
      <div class="top-grid"><label>Baseline suite<select id="strategy-suite-select"><option value="">Custom / no suite</option></select></label>
      <div style="align-self:end"><button id="strategy-suite-load" type="button">Load suite into Research Station</button></div></div>
      <div id="strategy-suite-detail" class="section-note" style="margin-top:10px"></div>`;
    anchor.insertAdjacentElement("afterend", card);
    const select = card.querySelector("#strategy-suite-select");
    const detail = card.querySelector("#strategy-suite-detail");
    const load = card.querySelector("#strategy-suite-load");
    for (const suite of SUITES) {
      const label = `${suite.name} — ${suite.status.toUpperCase()}`;
      select.append(new Option(label, suite.id));
    }
    const currentId = (new URL(window.location.href).searchParams.get("suite") || "").trim();
    if (currentId && suiteById(currentId)) select.value = currentId;
    const refresh = () => {
      const suite = suiteById(select.value);
      if (!suite) {
        detail.innerHTML = "Build a custom indicator suite directly below, or select one of the twenty research baselines.";
        load.disabled = true;
        return;
      }
      const missing = suite.unresolved.length ? `<br><strong>Unresolved:</strong> ${suite.unresolved.join(", ")}` : "";
      detail.innerHTML = `<strong>${suite.status.toUpperCase()} · evidence origin ${suite.evidence} · ${suite.timeframe}</strong><br>${suite.description}<br><strong>Canonical recipe:</strong> ${suite.recipe.join(" → ")}${missing}`;
      load.disabled = suite.status !== "ready";
      load.textContent = suite.status === "ready" ? "Load suite into Research Station" : "Suite not executable yet";
    };
    select.addEventListener("change", refresh);
    load.addEventListener("click", () => {
      const suite = suiteById(select.value);
      if (suite?.status === "ready") window.location.assign(suiteLaunchUrl(suite));
    });
    refresh();
  };

  const axisParameterName = (suiteId, axis) => {
    const direct = {
      "TS-S01-CONSOLIDATION-BREAKOUT": { base_duration:"duration", tightness:"max_range_pct", trend_filter:"trend_filter", relative_volume:"volume_ratio" },
      "TS-S02-DONCHIAN-BREAKOUT": { channel_period:"expression" },
      "TS-S14-TIME-SERIES-MOMENTUM": { lookback:"expression" },
      "TS-S15-MA-CROSSOVER": { fast_period:"expression" },
      "TS-S16-MACD-TREND": { trend_period:"expression" },
      "TS-S17-RSI2-MEAN-REVERSION": { oversold_threshold:"expression" },
      "TS-S18-BB-RSI-MEAN-REVERSION": { oversold_threshold:"expression" },
    };
    return direct[suiteId]?.[axis] || "";
  };

  const installControlledIterationCard = () => {
    if (document.getElementById("controlled-iteration-card")) return;
    const url = new URL(window.location.href);
    const suite = suiteById((url.searchParams.get("suite") || "").trim());
    if (!suite || suite.status !== "ready") return;
    const form = document.getElementById("strategy-form");
    if (!form) return;
    const card = document.createElement("div");
    card.id = "controlled-iteration-card";
    card.className = "card";
    card.innerHTML = `<h2>Controlled next iteration</h2>
      <div class="section-note">Change one declared suite dimension while preserving every other query parameter. This creates a neighboring experiment rather than an uncontrolled redesign.</div>
      <div class="top-grid"><label>Dimension<select id="iteration-axis"><option value="">Choose one dimension</option></select></label>
      <label>New machine value<input id="iteration-value" type="text" placeholder="Enter a different value"></label>
      <div style="align-self:end"><button id="iteration-open" type="button">Prepare one-change run</button></div></div>
      <div id="iteration-status" class="subtle" style="margin-top:8px"></div>`;
    form.insertAdjacentElement("afterend", card);
    const axis = card.querySelector("#iteration-axis");
    const value = card.querySelector("#iteration-value");
    const open = card.querySelector("#iteration-open");
    const status = card.querySelector("#iteration-status");
    for (const name of suite.axes) {
      const parameter = axisParameterName(suite.id, name);
      const option = new Option(parameter ? name.replaceAll("_", " ") : `${name.replaceAll("_", " ")} — not machine-resolved`, name);
      option.disabled = !parameter;
      axis.append(option);
    }
    const refresh = () => {
      const parameter = axisParameterName(suite.id, axis.value);
      const current = parameter ? (url.searchParams.get(parameter) ?? suite.parameters[parameter] ?? "") : "";
      value.value = current;
      status.textContent = parameter ? `Current ${axis.value.replaceAll("_", " ")}: ${current}. Enter one different value; all other settings remain frozen.` : "Choose a machine-resolved dimension.";
    };
    axis.addEventListener("change", refresh);
    open.addEventListener("click", () => {
      const parameter = axisParameterName(suite.id, axis.value);
      const next = value.value.trim();
      const current = parameter ? (url.searchParams.get(parameter) ?? suite.parameters[parameter] ?? "") : "";
      if (!parameter) { status.textContent = "That dimension is not yet machine-resolved."; return; }
      if (!next || next === current) { status.textContent = "Choose a different non-empty value. An identical configuration is not a new iteration."; return; }
      const target = new URL(window.location.href);
      target.searchParams.delete("experiment");
      target.searchParams.delete("message");
      target.searchParams.set(parameter, next);
      const brain = (target.searchParams.get("brain") || activeBrainId()).trim();
      if (brain) target.searchParams.set("brain", brain);
      window.location.assign(target.pathname + target.search);
    });
    refresh();
  };

  const enhance = () => {
    installPrintRules();
    installBrainSessionCard().then(() => {
      installSuiteCard();
      installControlledIterationCard();
    });
    const card = document.getElementById("experiment-record");
    if (!card) return;
    const id = experimentId(card);
    rememberCurrentWork(id);
    addActions(card, id);
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", enhance, { once:true });
  else enhance();
})();
""".replace("__SUITE_JSON__", _SUITE_JSON)

__all__ = ["STRATEGY_BUILDER_RESEARCH_MEMORY_JS"]
