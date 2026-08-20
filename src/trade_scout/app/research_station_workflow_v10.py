"""Research Station v10: explicit iterative next-sweep execution."""

from __future__ import annotations

from typing import cast

from trade_scout.app import research_station_workflow_v8 as _v8
from trade_scout.app import research_station_workflow_v9 as _v9
from trade_scout.app import research_workbench_console as _console
from trade_scout.app.strategic_followup import build_exit_followup
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html
from trade_scout.app.strategy_builder_service import StrategyBuilderReport
from trade_scout.app.strategy_next_step import analyze_strategic_next_steps

_CONFIGURED = False

_ITERATIVE_NEXT_STEP_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;
  const runNext = document.getElementById('strategic-run-next');
  if (!runNext) return;

  runNext.addEventListener('click', () => {
    const form = document.getElementById('strategy-form');
    const variable = document.getElementById('sweep-variable');
    const from = document.getElementById('sweep-from');
    const to = document.getElementById('sweep-to');
    const step = document.getElementById('sweep-step');
    const modal = document.getElementById('strategic-next-step-modal');
    if (!form || !variable || !from || !to || !step) {
      window.alert('SCOUT could not find the Section 5 controls. Nothing was run.');
      return;
    }

    const nextVariable = runNext.dataset.sweepVariable;
    const nextFrom = runNext.dataset.sweepFrom;
    const nextTo = runNext.dataset.sweepTo;
    const nextStep = runNext.dataset.sweepStep;
    const optionExists = [...variable.options].some((option) => option.value === nextVariable);
    if (!nextVariable || !nextFrom || !nextTo || !nextStep || !optionExists) {
      window.alert(
        'SCOUT could not map this suggestion back to the current Section 5 variable. ' +
        'Nothing was run.'
      );
      return;
    }

    runNext.disabled = true;
    runNext.textContent = 'Preparing next sweep…';
    variable.value = nextVariable;
    variable.dispatchEvent(new Event('change', {bubbles:true}));

    // Entry-sweep controls rebuild and bind asynchronously after a variable change.
    // Wait one short turn before applying the machine range, then use the normal form
    // submission path so validation, Brain association, experiment recording and
    // failure diagnostics all remain active.
    window.setTimeout(() => {
      from.value = nextFrom;
      to.value = nextTo;
      step.value = nextStep;
      for (const node of [from, to, step]) {
        node.dispatchEvent(new Event('input', {bubbles:true}));
        node.dispatchEvent(new Event('change', {bubbles:true}));
      }
      if (modal) modal.hidden = true;
      document.body.classList.remove('strategic-next-step-modal-open');
      runNext.textContent = 'Starting next sweep…';
      form.requestSubmit();
    }, 100);
  });
})();
"""


def _render_next_steps_v10(report: StrategyBuilderReport) -> str:
    analysis = analyze_strategic_next_steps(report.comparison)
    followup = build_exit_followup(report.comparison)
    return render_strategic_next_step_html(analysis, followup)


def configure_research_station_runtime() -> None:
    """Install v9, then add explicit bounded follow-up execution without bypassing validation."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _v9.configure_research_station_runtime()
    _v8._render_next_steps = _render_next_steps_v10

    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    namespace = vars(_console)
    asset = cast(str, namespace[asset_name])
    if "strategic-run-next" not in asset:
        namespace[asset_name] = asset + "\n" + _ITERATIVE_NEXT_STEP_JS
    _CONFIGURED = True


serve_research_workbench_console = _console.serve_research_workbench_console

__all__ = ["configure_research_station_runtime", "serve_research_workbench_console"]
