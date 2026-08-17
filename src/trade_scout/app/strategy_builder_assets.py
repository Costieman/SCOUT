# ruff: noqa: E501
"""Self-hosted browser asset for the local Strategy Builder composer."""

STRATEGY_BUILDER_JS = r"""
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('strategy-form');
  if (!form) return;

  const catalog = JSON.parse($('strategy-catalog-json').textContent || '[]');
  const rules0 = JSON.parse($('initial-rules-json').textContent || '[]');
  const stops0 = JSON.parse($('initial-stops-json').textContent || '[]');
  const rules = $('rule-rows');
  const stops = $('stop-rows');

  const staticGroups = new Map();
  const indicatorChoices = [];
  for (const item of catalog) {
    if (!staticGroups.has(item.indicator_id)) {
      staticGroups.set(item.indicator_id, []);
      indicatorChoices.push([item.indicator_id, item.indicator_label]);
    }
    staticGroups.get(item.indicator_id).push(item);
  }
  indicatorChoices.push(['custom_moving_average', 'Moving average — custom parameters']);
  indicatorChoices.push(['bollinger_bands', 'Bollinger Bands — custom parameters']);

  const MA_METRICS = [
    ['ma_distance_pct', 'Price distance from moving average'],
    ['ma_cross_up', 'Price/source crosses above moving average'],
    ['ma_cross_down', 'Price/source crosses below moving average'],
  ];
  const BB_METRICS = [
    ['bb_upper_distance_pct', 'Distance from upper band'],
    ['bb_middle_distance_pct', 'Distance from middle band'],
    ['bb_lower_distance_pct', 'Distance from lower band'],
    ['bb_upper_reached', 'Session high reaches upper band'],
    ['bb_lower_reached', 'Session low reaches lower band'],
    ['bb_upper_cross_up', 'Price/source crosses above upper band'],
    ['bb_lower_cross_down', 'Price/source crosses below lower band'],
    ['bb_middle_cross_up', 'Price/source crosses above middle band'],
    ['bb_middle_cross_down', 'Price/source crosses below middle band'],
    ['bb_bandwidth_pct', 'Band width as % of middle band'],
    ['bb_position', 'Price position inside/outside bands'],
  ];
  const BINARY_METRICS = new Set([
    'ma_cross_up', 'ma_cross_down', 'bb_upper_reached', 'bb_lower_reached',
    'bb_upper_cross_up', 'bb_lower_cross_down', 'bb_middle_cross_up', 'bb_middle_cross_down',
  ]);

  function option(value, label, selected = false) {
    const node = document.createElement('option');
    node.value = value;
    node.textContent = label;
    node.selected = selected;
    return node;
  }

  function staticMetric(featureName) {
    return catalog.find((item) => item.feature_name === featureName) || null;
  }

  function numberToken(value) {
    let text = Number(value).toPrecision(8);
    if (text.includes('e')) {
      const [mantissa, exponent] = text.split('e');
      text = `${mantissa.replace(/0+$/, '').replace(/\.$/, '')}e${Number(exponent)}`;
    } else {
      text = text.replace(/0+$/, '').replace(/\.$/, '');
    }
    return text.replaceAll('-', 'm').replaceAll('.', 'p');
  }

  function parseParameterized(featureName) {
    if (!featureName || !featureName.startsWith('pi__')) return null;
    const parts = featureName.split('__');
    if (parts.length !== 6) return null;
    const family = parts[1];
    const metric = parts[2];
    const source = parts[3];
    const period = Number(parts[4].slice(1));
    if (!Number.isInteger(period)) return null;
    if (family === 'moving_average') {
      return {indicator: 'custom_moving_average', family, metric, source, period, maType: parts[5]};
    }
    if (family === 'bollinger_bands' && parts[5].startsWith('k')) {
      const deviations = Number(parts[5].slice(1).replaceAll('m', '-').replaceAll('p', '.'));
      return {indicator: 'bollinger_bands', family, metric, source, period, deviations};
    }
    return null;
  }

  function parameterizedFeatureName(row) {
    const indicator = row.querySelector('.rule-indicator').value;
    const metric = row.querySelector('.rule-metric').value;
    const source = row.querySelector('.param-source').value;
    const period = Number(row.querySelector('.param-period').value);
    if (!Number.isInteger(period) || period < 2 || period > 1000) {
      throw new Error('Indicator period must be an integer from 2 to 1000 sessions.');
    }
    if (indicator === 'custom_moving_average') {
      const maType = row.querySelector('.param-ma-type').value;
      return `pi__moving_average__${metric}__${source}__p${period}__${maType}`;
    }
    const deviations = Number(row.querySelector('.param-deviations').value);
    if (!Number.isFinite(deviations) || deviations < 0.01 || deviations > 20) {
      throw new Error('Bollinger standard deviations must be from 0.01 to 20.');
    }
    return `pi__bollinger_bands__${metric}__${source}__p${period}__k${numberToken(deviations)}`;
  }

  function parameterControls(row, parsed = null) {
    const indicator = row.querySelector('.rule-indicator').value;
    const meta = row.querySelector('.rule-meta');
    meta.replaceChildren();
    if (indicator !== 'custom_moving_average' && indicator !== 'bollinger_bands') return;

    const controls = document.createElement('div');
    controls.className = 'indicator-parameters';
    controls.innerHTML = `
      <label>Period <input class="param-period" type="number" min="2" max="1000" step="1" value="${parsed?.period ?? 20}"></label>
      <label>Source <select class="param-source"><option value="close">Close</option><option value="open">Open</option><option value="high">High</option><option value="low">Low</option></select></label>
    `;
    controls.querySelector('.param-source').value = parsed?.source || 'close';
    if (indicator === 'custom_moving_average') {
      const label = document.createElement('label');
      label.innerHTML = 'Average type <select class="param-ma-type"><option value="sma">SMA</option><option value="ema">EMA</option></select>';
      label.querySelector('select').value = parsed?.maType || 'sma';
      controls.append(label);
    } else {
      const label = document.createElement('label');
      label.innerHTML = `<span>Std deviations</span><input class="param-deviations" type="number" min="0.01" max="20" step="0.01" value="${parsed?.deviations ?? 2}">`;
      controls.append(label);
      const note = document.createElement('div');
      note.className = 'parameter-note';
      note.textContent = 'Middle band = SMA; dispersion = population standard deviation. Band reach uses the session high/low; crossover metrics use the selected price source from t-1 to t.';
      controls.append(note);
    }
    meta.append(controls);
  }

  function applyThresholdDefaults(row, force = true) {
    const indicator = row.querySelector('.rule-indicator').value;
    const metricSelect = row.querySelector('.rule-metric');
    const operator = row.querySelector('.rule-operator');
    const value = row.querySelector('.rule-value');
    const slider = row.querySelector('.rule-slider');
    const meta = row.querySelector('.rule-meta');

    if (indicator === 'custom_moving_average' || indicator === 'bollinger_bands') {
      const metric = metricSelect.value;
      const binary = BINARY_METRICS.has(metric);
      if (binary) {
        Object.assign(value, {min: 0, max: 1, step: 1});
        Object.assign(slider, {min: 0, max: 1, step: 1});
        if (force) { operator.value = '=='; value.value = 1; }
      } else if (metric === 'bb_position') {
        Object.assign(value, {min: -10, max: 10, step: 0.01});
        Object.assign(slider, {min: -10, max: 10, step: 0.01});
        if (force) { operator.value = '>='; value.value = 1; }
      } else {
        Object.assign(value, {min: -1000, max: 1000, step: 0.01});
        Object.assign(slider, {min: -1000, max: 1000, step: 0.01});
        if (force) { operator.value = '>'; value.value = 0; }
      }
      slider.value = value.value;
      return;
    }

    const metric = staticMetric(metricSelect.value);
    if (!metric) return;
    Object.assign(value, {min: metric.min_value, max: metric.max_value, step: metric.step});
    Object.assign(slider, {min: metric.min_value, max: metric.max_value, step: metric.step});
    if (force) { operator.value = metric.default_operator; value.value = metric.default_value; }
    slider.value = value.value;
    meta.textContent = `${metric.parameter_summary} · ${metric.unit_label} · ${metric.description}`;
  }

  function fillMetrics(row, selectedFeature = null) {
    const indicator = row.querySelector('.rule-indicator').value;
    const metricSelect = row.querySelector('.rule-metric');
    const parsed = parseParameterized(selectedFeature);
    metricSelect.replaceChildren();
    if (indicator === 'custom_moving_average') {
      for (const [value, label] of MA_METRICS) metricSelect.append(option(value, label, parsed?.metric === value));
    } else if (indicator === 'bollinger_bands') {
      for (const [value, label] of BB_METRICS) metricSelect.append(option(value, label, parsed?.metric === value));
    } else {
      const metrics = staticGroups.get(indicator) || [];
      for (const item of metrics) metricSelect.append(option(item.feature_name, item.metric_label, item.feature_name === selectedFeature));
      if (!metrics.some((item) => item.feature_name === selectedFeature) && metrics[0]) metricSelect.value = metrics[0].feature_name;
    }
    parameterControls(row, parsed);
    applyThresholdDefaults(row, selectedFeature === null);
  }

  function ruleRow(rule = null) {
    const parsed = parseParameterized(rule?.feature_name);
    const staticItem = staticMetric(rule?.feature_name);
    const selectedIndicator = parsed?.indicator || staticItem?.indicator_id || indicatorChoices[0][0];
    const row = document.createElement('div');
    row.className = 'composer-row rule-row';
    row.innerHTML = `
      <label>Join<select class="rule-join"><option value="and">AND</option><option value="or">OR</option></select></label>
      <label>Indicator<select class="rule-indicator"></select></label>
      <label>Metric / trigger<select class="rule-metric"></select></label>
      <label>Relationship<select class="rule-operator"><option>&gt;</option><option>&gt;=</option><option>&lt;</option><option>&lt;=</option><option>==</option><option>!=</option></select></label>
      <label>Threshold<input class="rule-value" type="number"></label>
      <label class="slider-wrap">Fine control<input class="rule-slider" type="range"></label>
      <button class="remove-row" type="button">Remove</button>
      <div class="rule-meta"></div>
    `;
    const indicator = row.querySelector('.rule-indicator');
    for (const [value, label] of indicatorChoices) indicator.append(option(value, label, value === selectedIndicator));
    row.querySelector('.rule-join').value = rule?.join || 'and';
    fillMetrics(row, rule?.feature_name || null);
    if (rule) {
      row.querySelector('.rule-operator').value = rule.operator;
      row.querySelector('.rule-value').value = rule.value;
      row.querySelector('.rule-slider').value = rule.value;
    }
    indicator.addEventListener('change', () => fillMetrics(row, null));
    row.querySelector('.rule-metric').addEventListener('change', () => applyThresholdDefaults(row, true));
    row.querySelector('.rule-value').addEventListener('input', () => row.querySelector('.rule-slider').value = row.querySelector('.rule-value').value);
    row.querySelector('.rule-slider').addEventListener('input', () => row.querySelector('.rule-value').value = row.querySelector('.rule-slider').value);
    row.querySelector('.remove-row').addEventListener('click', () => { row.remove(); normalizeFirstRule(); });
    return row;
  }

  function normalizeFirstRule() {
    [...rules.querySelectorAll('.rule-row')].forEach((row, index) => {
      const join = row.querySelector('.rule-join');
      join.disabled = index === 0;
      if (index === 0) join.value = 'and';
    });
  }
  function addRule(rule = null) { rules.append(ruleRow(rule)); normalizeFirstRule(); }

  const stopBounds = (family) => (family === 'fixed' || family === 'trailing')
    ? {min: 0.01, max: 99.99, step: 0.01, unit: '%'}
    : {min: 0.01, max: 20, step: 0.01, unit: 'x ATR'};

  function stopRow(stop = null) {
    const row = document.createElement('div');
    row.className = 'composer-row stop-row';
    row.innerHTML = '<label>Exit type<select class="stop-family"><option value="fixed">Fixed % stop</option><option value="trailing">Trailing % stop</option><option value="atr">ATR stop</option><option value="trailing_atr">Trailing ATR stop</option></select></label><label>Exact value<input class="stop-value" type="number"></label><label class="slider-wrap">Slider<input class="stop-slider" type="range"></label><div class="stop-unit"></div><button class="remove-row" type="button">Remove</button>';
    const family = row.querySelector('.stop-family');
    const value = row.querySelector('.stop-value');
    const slider = row.querySelector('.stop-slider');
    const unit = row.querySelector('.stop-unit');
    family.value = stop?.family || 'fixed';
    value.value = stop?.value || 5;
    function applyBounds() {
      const bounds = stopBounds(family.value);
      Object.assign(value, {min: bounds.min, max: bounds.max, step: bounds.step});
      Object.assign(slider, {min: bounds.min, max: bounds.max, step: bounds.step});
      let numeric = Number(value.value);
      if (!Number.isFinite(numeric) || numeric < bounds.min || numeric > bounds.max) numeric = family.value.includes('atr') ? 2 : 5;
      value.value = numeric;
      slider.value = numeric;
      unit.textContent = `${bounds.unit} · ${bounds.min} to ${bounds.max}`;
    }
    family.addEventListener('change', applyBounds);
    value.addEventListener('input', () => slider.value = value.value);
    slider.addEventListener('input', () => value.value = slider.value);
    row.querySelector('.remove-row').addEventListener('click', () => row.remove());
    applyBounds();
    return row;
  }

  function hidden(name, value) {
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = name; input.value = value; input.dataset.gen = '1';
    form.append(input);
  }

  function compileRule(row, index) {
    const indicator = row.querySelector('.rule-indicator').value;
    const feature = (indicator === 'custom_moving_average' || indicator === 'bollinger_bands')
      ? parameterizedFeatureName(row)
      : row.querySelector('.rule-metric').value;
    const value = Number(row.querySelector('.rule-value').value);
    if (!Number.isFinite(value)) throw new Error('Every visual rule needs a finite threshold.');
    return {
      feature,
      operator: row.querySelector('.rule-operator').value,
      value,
      join: index === 0 ? 'and' : row.querySelector('.rule-join').value,
    };
  }

  $('add-rule').addEventListener('click', () => addRule());
  $('add-stop').addEventListener('click', () => stops.append(stopRow()));
  $('clear-stops').addEventListener('click', () => stops.replaceChildren());

  form.addEventListener('submit', (event) => {
    form.querySelectorAll('[data-gen="1"]').forEach((node) => node.remove());
    try {
      if ($('entry-mode-visual').checked) {
        const built = [...rules.querySelectorAll('.rule-row')].map(compileRule);
        if (!built.length) throw new Error('Add at least one entry condition.');
        let expression = `${built[0].feature} ${built[0].operator} ${built[0].value}`;
        for (const rule of built.slice(1)) expression = `(${expression} ${rule.join} ${rule.feature} ${rule.operator} ${rule.value})`;
        hidden('expression', expression);
        for (const rule of built) {
          hidden('rule_feature', rule.feature);
          hidden('rule_operator', rule.operator);
          hidden('rule_value', String(rule.value));
          hidden('rule_join', rule.join);
        }
      } else {
        const expression = $('advanced-expression').value.trim();
        if (!expression) throw new Error('Advanced expression cannot be empty.');
        hidden('expression', expression);
      }
      const grouped = {fixed: [], trailing: [], atr: [], trailing_atr: []};
      for (const row of stops.querySelectorAll('.stop-row')) {
        const family = row.querySelector('.stop-family').value;
        const value = Number(row.querySelector('.stop-value').value);
        const bounds = stopBounds(family);
        if (!Number.isFinite(value) || value < bounds.min || value > bounds.max) throw new Error(`Exit value must be ${bounds.min} to ${bounds.max}.`);
        grouped[family].push(value);
      }
      hidden('fixed_stops', grouped.fixed.join(','));
      hidden('trailing_stops', grouped.trailing.join(','));
      hidden('atr_stops', grouped.atr.join(','));
      hidden('trailing_atr', grouped.trailing_atr.join(','));
    } catch (error) {
      event.preventDefault();
      $('composer-error').hidden = false;
      $('composer-error').textContent = error.message || String(error);
    }
  });

  if (rules0.length) rules0.forEach(addRule);
  else addRule({feature_name: 'return_20', operator: '>=', value: 0.05, join: 'and'});
  stops0.forEach((stop) => stops.append(stopRow(stop)));

  function syncMode() {
    $('visual-builder-panel').hidden = !$('entry-mode-visual').checked;
    $('advanced-builder-panel').hidden = !$('entry-mode-advanced').checked;
  }
  $('entry-mode-visual').addEventListener('change', syncMode);
  $('entry-mode-advanced').addEventListener('change', syncMode);
  syncMode();
})();
"""

__all__ = ["STRATEGY_BUILDER_JS"]
