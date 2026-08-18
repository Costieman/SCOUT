# ruff: noqa: E501
"""Presentation-only controls that bind configured entry-indicator parameters to Section 5."""

STRATEGY_BUILDER_ENTRY_SWEEP_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;
  const form = document.getElementById('strategy-form');
  const rules = document.getElementById('rule-rows');
  const variable = document.getElementById('sweep-variable');
  const from = document.getElementById('sweep-from');
  const to = document.getElementById('sweep-to');
  const step = document.getElementById('sweep-step');
  const preview = document.getElementById('sweep-preview');
  if (!form || !rules || !variable || !from || !to || !step || !preview) return;

  const query = new URLSearchParams(window.location.search);
  const restoredFeature = query.get('entry_sweep_feature');
  const restoredParameter = query.get('entry_sweep_parameter');
  const restoredFrom = query.get('entry_sweep_from');
  const restoredTo = query.get('entry_sweep_to');
  const restoredStep = query.get('entry_sweep_step');
  let restored = false;
  let rebuildQueued = false;

  const numberToken = (value) => Number(value).toFixed(8)
    .replace(/0+$/, '').replace(/\.$/, '').replaceAll('-', 'm').replaceAll('.', 'p');
  const actualMetric = (metric) => metric === 'ma_above' || metric === 'ma_below'
    ? 'ma_distance_pct' : metric;

  function featureName(row) {
    const family = row.querySelector('.rule-indicator')?.value;
    if (!family || family === 'legacy_fixed') return null;
    const metric = actualMetric(row.querySelector('.rule-metric')?.value || '');
    const source = row.querySelector('.param-source')?.value || 'close';
    const period = Number(row.querySelector('.param-period')?.value || 20);
    let suffix = 'standard';
    if (family === 'moving_average') suffix = row.querySelector('.param-ma-type')?.value || 'sma';
    else if (family === 'bollinger_bands') suffix = `k${numberToken(row.querySelector('.param-deviations')?.value || 2)}`;
    else if (family === 'macd') {
      const fast = row.querySelector('.param-fast')?.value || 12;
      const slow = row.querySelector('.param-slow')?.value || 26;
      const signal = row.querySelector('.param-signal')?.value || 9;
      suffix = `f${fast}s${slow}g${signal}`;
    } else if (family === 'rsi' || family === 'atr') suffix = 'wilder';
    else if (family === 'historical_volatility') suffix = 'annual252';
    else if (['relative_volume', 'average_dollar_volume', 'prior_high'].includes(family)) suffix = 'prior';
    return `pi__${family}__${metric}__${source}__p${period}__${suffix}`;
  }

  function optionValue(feature, parameter) {
    return `entry::${feature}::${parameter}`;
  }

  function parsedEntrySelection() {
    if (!variable.value.startsWith('entry::')) return null;
    const parts = variable.value.split('::');
    if (parts.length !== 3) return null;
    return {feature: parts[1], parameter: parts[2]};
  }

  function parameterCandidates(row, index) {
    const family = row.querySelector('.rule-indicator')?.value;
    const feature = featureName(row);
    if (!feature) return [];
    const indicator = row.querySelector('.rule-indicator')?.selectedOptions?.[0]?.textContent || 'Indicator';
    const prefix = `Entry ${index + 1} · ${indicator}`;
    if (family === 'macd') {
      return [
        {feature, parameter: 'fast_period', label: `${prefix} · Fast EMA period`, selector: '.param-fast'},
        {feature, parameter: 'slow_period', label: `${prefix} · Slow EMA period`, selector: '.param-slow'},
        {feature, parameter: 'signal_period', label: `${prefix} · Signal EMA period`, selector: '.param-signal'},
      ];
    }
    const result = [{feature, parameter: 'period', label: `${prefix} · Period / lookback`, selector: '.param-period'}];
    if (family === 'bollinger_bands') {
      result.push({feature, parameter: 'standard_deviations', label: `${prefix} · Standard deviations`, selector: '.param-deviations'});
    }
    return result;
  }

  function rebuildOptions() {
    const selected = variable.value;
    variable.querySelectorAll('.entry-sweep-option').forEach((node) => node.remove());
    const group = document.createElement('optgroup');
    group.label = 'Entry indicator parameters'; group.className = 'entry-sweep-option';
    [...rules.querySelectorAll('.rule-row')].forEach((row, index) => {
      for (const candidate of parameterCandidates(row, index)) {
        const option = document.createElement('option');
        option.className = 'entry-sweep-option';
        option.value = optionValue(candidate.feature, candidate.parameter);
        option.textContent = candidate.label;
        option.dataset.ruleIndex = String(index);
        option.dataset.controlSelector = candidate.selector;
        group.append(option);
      }
    });
    if (group.children.length) variable.append(group);
    if ([...variable.options].some((option) => option.value === selected)) variable.value = selected;
    if (!restored && restoredFeature && restoredParameter) {
      const target = optionValue(restoredFeature, restoredParameter);
      if ([...variable.options].some((option) => option.value === target)) {
        variable.value = target;
        restored = true;
      }
    }
    syncEntrySweep(true);
  }

  function scheduleRebuild() {
    if (rebuildQueued) return;
    rebuildQueued = true;
    queueMicrotask(() => {
      rebuildQueued = false;
      rebuildOptions();
    });
  }

  function mutationOnlyTouchesSweepBadges(mutation) {
    const nodes = [...mutation.addedNodes, ...mutation.removedNodes];
    return nodes.length > 0 && nodes.every(
      (node) => node instanceof HTMLElement && node.classList.contains('entry-sweep-badge')
    );
  }

  function bounds(selection) {
    const option = [...variable.options].find((item) => item.value === variable.value);
    const index = Number(option?.dataset.ruleIndex);
    const selector = option?.dataset.controlSelector;
    const row = Number.isInteger(index) ? rules.querySelectorAll('.rule-row')[index] : null;
    const current = Number(row?.querySelector(selector)?.value || 0);
    if (selection.parameter === 'standard_deviations') {
      return {min: 0.01, max: 20, step: 0.01, start: Math.max(0.25, current - 1), end: Math.min(20, current + 1), increment: 0.25};
    }
    if (selection.parameter === 'fast_period') {
      return {min: 2, max: 999, step: 1, start: Math.max(2, current - 6), end: current + 6, increment: 2};
    }
    if (selection.parameter === 'slow_period') {
      return {min: 3, max: 1000, step: 1, start: Math.max(3, current - 10), end: Math.min(1000, current + 10), increment: 2};
    }
    if (selection.parameter === 'signal_period') {
      return {min: 2, max: 1000, step: 1, start: Math.max(2, current - 4), end: Math.min(1000, current + 6), increment: 1};
    }
    const spread = current >= 100 ? 50 : current >= 30 ? 20 : 10;
    const increment = current >= 100 ? 10 : current >= 30 ? 5 : 1;
    return {min: 2, max: 1000, step: 1, start: Math.max(2, current - spread), end: Math.min(1000, current + spread), increment};
  }

  function unlockBoundControl() {
    document.querySelectorAll('[data-entry-sweep-bound="1"]').forEach((node) => {
      node.disabled = false;
      delete node.dataset.entrySweepBound;
      node.style.removeProperty('opacity');
    });
    document.querySelectorAll('.entry-sweep-badge').forEach((node) => node.remove());
  }

  function lockBoundControl() {
    unlockBoundControl();
    const option = [...variable.options].find((item) => item.value === variable.value);
    if (!option?.dataset.controlSelector) return;
    const row = rules.querySelectorAll('.rule-row')[Number(option.dataset.ruleIndex)];
    const control = row?.querySelector(option.dataset.controlSelector);
    if (!control) return;
    control.disabled = true; control.dataset.entrySweepBound = '1'; control.style.opacity = '.55';
    const slider = row.querySelector(`${option.dataset.controlSelector}-slider`);
    if (slider) { slider.disabled = true; slider.dataset.entrySweepBound = '1'; slider.style.opacity = '.55'; }
    const summary = row.querySelector('.rule-summary-main') || row;
    const badge = document.createElement('span');
    badge.className = 'entry-sweep-badge';
    badge.textContent = 'UNDER TEST IN SECTION 5';
    badge.style.cssText = 'font-size:10px;color:#f1c84b;border:1px solid #6d5b24;border-radius:999px;padding:3px 7px;';
    summary.append(badge);
  }

  function syncEntrySweep(useRestoredValues = false) {
    const selection = parsedEntrySelection();
    if (!selection) { unlockBoundControl(); return; }
    const spec = bounds(selection);
    for (const input of [from, to, step]) {
      input.disabled = false; input.min = String(spec.min); input.max = String(spec.max); input.step = String(spec.step);
    }
    if (useRestoredValues && restoredFeature) {
      from.value = restoredFrom || String(spec.start);
      to.value = restoredTo || String(spec.end);
      step.value = restoredStep || String(spec.increment);
    } else {
      from.value = String(spec.start); to.value = String(spec.end); step.value = String(spec.increment);
    }
    lockBoundControl();
    preview.innerHTML = `<strong>Entry parameter under test:</strong> ${variable.selectedOptions[0]?.textContent}. Each value creates its own point-in-time entry population. SCOUT will report N for every child and evaluate hold-to-maximum-period so stop selection remains a separate research dimension.`;
  }

  variable.addEventListener('change', () => queueMicrotask(() => syncEntrySweep(false)));
  rules.addEventListener('change', scheduleRebuild);
  new MutationObserver((mutations) => {
    if (mutations.every(mutationOnlyTouchesSweepBadges)) return;
    scheduleRebuild();
  }).observe(rules, {childList: true, subtree: true});

  form.addEventListener('submit', () => {
    const selection = parsedEntrySelection();
    if (!selection) return;
    form.querySelectorAll('[data-entry-sweep-gen="1"]').forEach((node) => node.remove());
    const add = (name, value) => {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = name; input.value = value;
      input.dataset.entrySweepGen = '1'; form.append(input);
    };
    add('entry_sweep_feature', selection.feature);
    add('entry_sweep_parameter', selection.parameter);
    add('entry_sweep_from', from.value);
    add('entry_sweep_to', to.value);
    add('entry_sweep_step', step.value);
    variable.removeAttribute('name');
    variable.value = '';
  }, true);

  rebuildOptions();
})();
"""

__all__ = ["STRATEGY_BUILDER_ENTRY_SWEEP_JS"]
