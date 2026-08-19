# ruff: noqa: E501
"""Second-pass Research Station workflow repair.

This layer fixes three UI/runtime regressions without changing analytical definitions:

* loading a strategy suite prepares an editable request but never executes research;
* a one-variable exit sweep locks only the swept component and leaves its partner editable;
* the explicit research run action is moved into a persistent bottom action bar.
"""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from typing import cast
from urllib.parse import parse_qs

from trade_scout.app import research_workbench_console as _console
from trade_scout.app.entry_strategy_registry import EntryFamily, available_entry_strategies
from trade_scout.app.exit_policy_lab_service import parse_multiple_grid, parse_percentage_grid
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.research_station_integration import (
    configure_research_station_runtime as _configure_research_station_runtime_v1,
)
from trade_scout.app.strategy_builder_exit_plans import parse_exit_plan_tokens
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.app.strategy_builder_service import StrategyBuilderRequest
from trade_scout.app.strategy_builder_surface import render_strategy_builder_html
from trade_scout.app.strategy_suite_workflow import built_in_suite_launch_plans
from trade_scout.patterns.consolidation_breakout import TrendFilter
from trade_scout.risk.exit_policies import SameBarExitPolicy
from trade_scout.statistics.strategy_research import available_strategy_features


RecordedPageBuilder = Callable[
    [str, LocalConsoleConfig, StrategyBuilderExperimentRecorder], tuple[HTTPStatus, str]
]
_ORIGINAL_RECORDED_PAGE = cast(RecordedPageBuilder, getattr(_console, "build_recorded_strategy_page"))
_CONFIGURED = False


def _one(
    parameters: dict[str, list[str]],
    name: str,
    *,
    default: str | None = None,
) -> str:
    values = parameters.get(name)
    if not values:
        if default is None:
            raise ValueError(f"missing query parameter {name}")
        return default
    if len(values) != 1:
        raise ValueError(f"query parameter {name} must appear once")
    return values[0]


def _optional_volume_ratio(value: str) -> float | None:
    if value.strip().lower() == "none":
        return None
    result = float(value)
    if result <= 0:
        raise ValueError("volume_ratio must be positive or 'none'")
    return result


def _configuration_only_page(query: str, config: LocalConsoleConfig) -> tuple[HTTPStatus, str]:
    """Resolve and render a Strategy Builder request without running analytics."""

    source = config.strategy_builder_source
    entries = available_entry_strategies()
    features = available_strategy_features()
    if source is None:
        return (
            HTTPStatus.SERVICE_UNAVAILABLE,
            render_strategy_builder_html(
                universes=(),
                entries=entries,
                features=features,
                error="Strategy Builder configuration preview requires a canonical source.",
            ),
        )
    try:
        universes = source.available_universes()
    except Exception as exc:
        return (
            HTTPStatus.SERVICE_UNAVAILABLE,
            render_strategy_builder_html(
                universes=(),
                entries=entries,
                features=features,
                error=f"Cannot load research-universe scope: {type(exc).__name__}: {exc}",
            ),
        )

    parameters = parse_qs(query, keep_blank_values=True)
    request: StrategyBuilderRequest | None = None
    try:
        same_bar_policy = SameBarExitPolicy(
            _one(parameters, "same_bar_policy", default=SameBarExitPolicy.STOP_FIRST.value)
        )
        plan_tokens = parameters.get("exit_plan", [])
        managed_plans = parse_exit_plan_tokens(plan_tokens, same_bar_policy=same_bar_policy)
        using_managed = bool(plan_tokens)
        request = StrategyBuilderRequest(
            universe_id=_one(parameters, "universe", default="reviewed_canonical"),
            entry_family=EntryFamily(
                _one(parameters, "entry_family", default=EntryFamily.FEATURE_EXPRESSION.value)
            ),
            lookback_years=int(_one(parameters, "lookback_years", default="2")),
            horizon=int(_one(parameters, "horizon", default="20")),
            expression=_one(
                parameters,
                "expression",
                default=(
                    "return_20 >= 0.05 and relative_volume_20 >= 1.5 "
                    "and distance_sma_200_pct > 0"
                ),
            ),
            rank_feature=_one(parameters, "rank_feature", default="return_20"),
            descending=_one(parameters, "rank_direction", default="desc") == "desc",
            per_session_limit=int(_one(parameters, "per_session_limit", default="500")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(
                    parameters,
                    "trend_filter",
                    default=TrendFilter.ABOVE_SMA_50_100_200.value,
                )
            ),
            min_breakout_volume_ratio=_optional_volume_ratio(
                _one(parameters, "volume_ratio", default="none")
            ),
            fixed_percentages=(
                ()
                if using_managed
                else parse_percentage_grid(_one(parameters, "fixed_stops", default=""))
            ),
            trailing_percentages=(
                ()
                if using_managed
                else parse_percentage_grid(_one(parameters, "trailing_stops", default=""))
            ),
            atr_multiples=(
                ()
                if using_managed
                else parse_multiple_grid(_one(parameters, "atr_stops", default=""))
            ),
            trailing_atr_multiples=(
                ()
                if using_managed
                else parse_multiple_grid(_one(parameters, "trailing_atr", default=""))
            ),
            managed_exit_plans=managed_plans,
            same_bar_policy=same_bar_policy,
            entry_slippage_bps=float(_one(parameters, "entry_slip", default="0")),
            exit_slippage_bps=float(_one(parameters, "exit_slip", default="0")),
            stop_slippage_bps=float(_one(parameters, "stop_slip", default="0")),
            commission_bps_per_side=float(_one(parameters, "commission", default="0")),
        )
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            report=None,
        )
        return HTTPStatus.OK, html
    except ValueError as exc:
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            error=str(exc),
        )
        return HTTPStatus.BAD_REQUEST, html


def _recorded_page_with_configuration_preview(
    query: str,
    config: LocalConsoleConfig,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    parameters = parse_qs(query, keep_blank_values=True)
    if _one(parameters, "load_only", default="0") == "1":
        return _configuration_only_page(query, config)
    return _ORIGINAL_RECORDED_PAGE(query, config, recorder)


def _suite_parameters_json() -> str:
    import json

    payload = {
        plan.suite_id: dict(plan.builder_parameters)
        for plan in built_in_suite_launch_plans()
        if plan.executable
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


_RESEARCH_STATION_V2_JS = r"""
(() => {
  "use strict";
  const SUITE_PARAMETERS = __SUITE_PARAMETERS__;
  const ACTIVE_BRAIN_KEY = "trade-scout:research-brain:active";

  const loadSuiteWithoutRunning = (suiteId) => {
    const parameters = SUITE_PARAMETERS[suiteId];
    if (!parameters) return;
    const url = new URL("/research/strategy", window.location.origin);
    for (const [key, value] of Object.entries(parameters)) {
      url.searchParams.set(key, String(value));
    }
    url.searchParams.set("suite", suiteId);
    url.searchParams.set("load_only", "1");
    const brain = localStorage.getItem(ACTIVE_BRAIN_KEY) || "";
    if (brain) url.searchParams.set("brain", brain);
    window.location.assign(url.pathname + url.search);
  };

  document.addEventListener("click", (event) => {
    const target = event.target;
    const button = target instanceof Element ? target.closest("#strategy-suite-load") : null;
    if (!button) return;
    const select = document.getElementById("strategy-suite-select");
    const suiteId = select?.value || "";
    if (!suiteId || !SUITE_PARAMETERS[suiteId]) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    loadSuiteWithoutRunning(suiteId);
  }, true);

  const installPersistentRunDock = () => {
    const form = document.getElementById("strategy-form");
    const run = form?.querySelector('button.primary[type="submit"]');
    if (!form || !run || document.getElementById("strategy-run-dock")) return;
    const style = document.createElement("style");
    style.id = "strategy-run-dock-style";
    style.textContent = `
      body { padding-bottom: 88px; }
      #strategy-run-dock {
        position: fixed; left: 50%; bottom: 12px; transform: translateX(-50%);
        width: min(1800px, calc(100vw - 28px)); z-index: 1000;
        display: flex; align-items: center; gap: 14px; padding: 10px 12px;
        border: 1px solid #6d5b24; border-radius: 12px;
        background: rgba(18, 23, 32, .97); box-shadow: 0 10px 30px rgba(0,0,0,.38);
        backdrop-filter: blur(8px);
      }
      #strategy-run-dock .run-context { color:#98a6b8; font-size:12px; white-space:nowrap; }
      #strategy-run-dock .primary { flex: 1; min-height: 48px; font-size: 16px; }
      @media(max-width:760px) {
        #strategy-run-dock { flex-direction:column; gap:6px; }
        #strategy-run-dock .run-context { white-space:normal; text-align:center; }
        #strategy-run-dock .primary { width:100%; }
      }
      @media print { #strategy-run-dock { display:none !important; } body { padding-bottom:0; } }
    `;
    document.head.append(style);
    const oldToolbar = run.closest(".toolbar");
    const dock = document.createElement("div");
    dock.id = "strategy-run-dock";
    const context = document.createElement("div");
    context.className = "run-context";
    context.textContent = "Configuration only changes when you edit controls. Research starts only here.";
    run.textContent = "Run research";
    dock.append(context, run);
    form.append(dock);
    if (oldToolbar && !oldToolbar.children.length) oldToolbar.remove();
  };

  const sweepComponent = (value) => value.startsWith("target_") ? "target" : (value ? "stop" : "");

  const syncSweepEditability = () => {
    const variable = document.getElementById("sweep-variable");
    const exits = document.getElementById("exit-plan-rows");
    if (!variable || !exits) return;
    const component = sweepComponent(variable.value);
    for (const row of exits.querySelectorAll(".exit-plan-row")) {
      row.style.pointerEvents = "auto";
      const bound = row.dataset.sweepBound === "1";
      const stopFamily = row.querySelector(".exit-stop-family");
      const stopValue = row.querySelector(".exit-stop-value");
      const stopSlider = row.querySelector(".exit-stop-slider");
      const targetFamily = row.querySelector(".exit-target-family");
      const targetValue = row.querySelector(".exit-target-value");
      const targetSlider = row.querySelector(".exit-target-slider");

      if (!bound || !component) {
        if (stopFamily) stopFamily.disabled = false;
        if (stopValue) stopValue.disabled = false;
        if (stopSlider) stopSlider.disabled = false;
        if (targetFamily) targetFamily.disabled = false;
        const hasTarget = targetFamily?.value && targetFamily.value !== "none";
        if (targetValue) targetValue.disabled = !hasTarget;
        if (targetSlider) targetSlider.disabled = !hasTarget;
        continue;
      }

      if (component === "stop") {
        if (stopFamily) stopFamily.disabled = true;
        if (stopValue) stopValue.disabled = true;
        if (stopSlider) stopSlider.disabled = true;
        if (targetFamily) targetFamily.disabled = false;
        const hasTarget = targetFamily?.value && targetFamily.value !== "none";
        if (targetValue) targetValue.disabled = !hasTarget;
        if (targetSlider) targetSlider.disabled = !hasTarget;
      } else {
        if (stopFamily) stopFamily.disabled = false;
        if (stopValue) stopValue.disabled = false;
        if (stopSlider) stopSlider.disabled = false;
        if (targetFamily) targetFamily.disabled = true;
        if (targetValue) targetValue.disabled = true;
        if (targetSlider) targetSlider.disabled = true;
      }
    }

    const notice = document.getElementById("sweep-bound-notice");
    if (notice && component && !notice.hidden) {
      let helper = notice.querySelector(".sweep-edit-helper");
      if (!helper) {
        helper = document.createElement("div");
        helper.className = "sweep-edit-helper";
        helper.style.marginTop = "6px";
        notice.append(helper);
      }
      helper.textContent = component === "stop"
        ? "Only the stop parameter under test is locked in Section 3. Profit-target settings remain editable."
        : "Only the profit-target parameter under test is locked in Section 3. Protective-stop settings remain editable.";
    }
  };

  const installExitPlanCleanup = () => {
    const exits = document.getElementById("exit-plan-rows");
    const clear = document.getElementById("clear-exit-plans");
    if (!exits || !clear || exits.dataset.cleanupWired === "1") return;
    exits.dataset.cleanupWired = "1";
    clear.textContent = "Clear all exit plans";
    const refresh = () => {
      clear.hidden = !exits.querySelector(".exit-plan-row");
      setTimeout(syncSweepEditability, 0);
    };
    new MutationObserver(refresh).observe(exits, { childList: true, subtree: true });
    document.getElementById("sweep-variable")?.addEventListener("change", () => setTimeout(syncSweepEditability, 0));
    exits.addEventListener("change", () => setTimeout(syncSweepEditability, 0));
    refresh();
  };

  const install = () => {
    installPersistentRunDock();
    installExitPlanCleanup();
    syncSweepEditability();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(install, 0), { once: true });
  } else {
    setTimeout(install, 0);
  }
})();
""".replace("__SUITE_PARAMETERS__", _suite_parameters_json())


def configure_research_station_runtime() -> None:
    """Install the previous repair plus the configuration-preview and UI fixes."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _configure_research_station_runtime_v1()
    setattr(_console, "build_recorded_strategy_page", _recorded_page_with_configuration_preview)
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    asset = cast(str, getattr(_console, asset_name))
    if "strategy-run-dock" not in asset:
        setattr(_console, asset_name, asset + "\n" + _RESEARCH_STATION_V2_JS)
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
