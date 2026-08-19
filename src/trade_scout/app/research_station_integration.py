"""Runtime integration fixes for Strategy Builder suites and Research Brains.

This layer keeps suite selection configuration-only, enables same-origin Brain discovery under the
workbench CSP, supports inline Brain creation, and automatically associates completed experiments
with the active Brain. It deliberately does not change analytical definitions.
"""

from __future__ import annotations

import json

from trade_scout.app import research_workbench_console as _console
from trade_scout.app.strategy_suite_workflow import built_in_suite_launch_plans


def _suite_parameters_json() -> str:
    payload = {
        plan.suite_id: dict(plan.builder_parameters)
        for plan in built_in_suite_launch_plans()
        if plan.executable
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


_RESEARCH_STATION_FIX_JS = r"""
(() => {
  "use strict";
  const SUITE_PARAMETERS = __SUITE_PARAMETERS__;
  const ACTIVE_BRAIN_KEY = "trade-scout:research-brain:active";

  const setControl = (form, name, value) => {
    const control = form.elements.namedItem(name);
    if (!control) return false;
    if (control instanceof RadioNodeList) {
      control.value = String(value);
      return true;
    }
    control.value = String(value);
    control.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  };

  const installSafeSuiteLoader = () => {
    const oldButton = document.getElementById("strategy-suite-load");
    const select = document.getElementById("strategy-suite-select");
    const form = document.getElementById("strategy-form");
    if (!oldButton || !select || !form || oldButton.dataset.safeLoader === "1") return;
    const button = oldButton.cloneNode(true);
    button.dataset.safeLoader = "1";
    oldButton.replaceWith(button);
    button.addEventListener("click", () => {
      const suiteId = select.value;
      const parameters = SUITE_PARAMETERS[suiteId];
      if (!parameters) return;
      let applied = 0;
      for (const [name, value] of Object.entries(parameters)) {
        if (setControl(form, name, value)) applied += 1;
      }
      const url = new URL(window.location.href);
      url.searchParams.set("suite", suiteId);
      url.searchParams.delete("experiment");
      url.searchParams.delete("message");
      const brain = localStorage.getItem(ACTIVE_BRAIN_KEY) || "";
      if (brain) url.searchParams.set("brain", brain);
      history.replaceState({}, "", url.pathname + url.search);
      const detail = document.getElementById("strategy-suite-detail");
      if (detail) {
        const note = document.createElement("div");
        note.className = "section-note";
        note.style.marginTop = "10px";
        note.innerHTML = `<strong>Suite loaded — not run.</strong> ${applied} baseline controls were populated. Edit any research, stop, target, horizon, or filter settings you want, then press the normal Run button when you are ready.`;
        detail.appendChild(note);
      }
    });
  };

  const parseBrains = async () => {
    const response = await fetch("/research/brains", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error(`Brain inventory returned ${response.status}`);
    const doc = new DOMParser().parseFromString(await response.text(), "text/html");
    return [...doc.querySelectorAll('#research-brain-discovery-index option')]
      .map((option) => ({ id: option.value.trim(), name: option.textContent.trim() }))
      .filter((item) => item.id && item.name);
  };

  const repopulateBrainSelect = async (select, status) => {
    const prior = select.value || localStorage.getItem(ACTIVE_BRAIN_KEY) || "";
    const brains = await parseBrains();
    select.innerHTML = '<option value="">No brain selected — standalone research</option>';
    for (const brain of brains) select.append(new Option(brain.name, brain.id));
    if (prior && brains.some((brain) => brain.id === prior)) select.value = prior;
    if (select.value) localStorage.setItem(ACTIVE_BRAIN_KEY, select.value);
    status.textContent = brains.length
      ? `${brains.length} research brain${brains.length === 1 ? "" : "s"} available. Runs will be associated with the selected brain automatically.`
      : "No research brains exist yet. Create one here without leaving the Research Station.";
    return brains;
  };

  const installBrainControls = async () => {
    const card = document.getElementById("research-brain-session-card");
    const select = document.getElementById("research-brain-session-select");
    const status = document.getElementById("research-brain-session-status");
    if (!card || !select || !status || card.dataset.directBrains === "1") return;
    card.dataset.directBrains = "1";
    try { await repopulateBrainSelect(select, status); }
    catch (error) { status.textContent = `Could not load research brains: ${error.message}`; }

    const actions = card.querySelector(".top-grid > div:last-child");
    if (!actions) return;
    const create = document.createElement("button");
    create.type = "button";
    create.textContent = "+ New Brain";
    actions.prepend(create);
    create.addEventListener("click", async () => {
      const name = window.prompt("Brain name");
      if (!name?.trim()) return;
      const question = window.prompt("Research question for this Brain", `Research ${name.trim()}`);
      if (!question?.trim()) return;
      const body = new URLSearchParams({
        action: "create",
        name: name.trim(),
        research_question: question.trim(),
        actor: "research-station",
        focus_rules: "",
        notes: "Created directly from the Research Station.",
      });
      status.textContent = "Creating research brain…";
      const response = await fetch("/research/brains", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
        body: body.toString(),
      });
      if (!response.ok) {
        status.textContent = `Brain creation failed (${response.status}).`;
        return;
      }
      const brains = await repopulateBrainSelect(select, status);
      const created = brains.find((brain) => brain.name === name.trim());
      if (created) {
        select.value = created.id;
        localStorage.setItem(ACTIVE_BRAIN_KEY, created.id);
        select.dispatchEvent(new Event("change", { bubbles: true }));
        status.textContent = `Created and selected ${created.name}.`;
      }
    });
  };

  const experimentId = () => {
    const card = document.getElementById("experiment-record");
    if (!card) return "";
    for (const row of card.querySelectorAll("tr")) {
      if (row.querySelector("th")?.textContent.trim() === "Experiment ID") {
        return row.querySelector("td code")?.textContent.trim() || "";
      }
    }
    return "";
  };

  const autoAssociateRun = async () => {
    const brain = localStorage.getItem(ACTIVE_BRAIN_KEY) || "";
    const experiment = experimentId();
    if (!brain || !experiment) return;
    const key = `trade-scout:auto-brain:${brain}:${experiment}`;
    if (sessionStorage.getItem(key)) return;
    const body = new URLSearchParams({
      action: "add",
      brain_id: brain,
      experiment_id: experiment,
      actor: "research-station",
      note: "Automatically associated by the active Research Station Brain context.",
    });
    const response = await fetch("/research/brains", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
      body: body.toString(),
    });
    if (response.ok) sessionStorage.setItem(key, "1");
  };

  const install = () => {
    installSafeSuiteLoader();
    installBrainControls();
    autoAssociateRun();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(install, 0), { once: true });
  } else {
    setTimeout(install, 0);
  }
})();
""".replace("__SUITE_PARAMETERS__", _suite_parameters_json())


def configure_research_station_runtime() -> None:
    """Install the Research Station integration fixes before the local server starts."""

    original_csp = _console._csp_value

    def csp_with_same_origin_fetch() -> str:
        value = original_csp()
        if "connect-src" in value:
            return value
        return value + "; connect-src 'self'"

    _console._csp_value = csp_with_same_origin_fetch
    if "Suite loaded — not run." not in _console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS:
        _console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS += "\n" + _RESEARCH_STATION_FIX_JS


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
