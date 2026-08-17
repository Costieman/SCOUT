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

  const INDUSTRY = [
    ['moving_average', 'Moving Average (SMA / EMA)'],
    ['price_roc', 'Price Rate of Change (ROC)'],
    ['rsi', 'Relative Strength Index (RSI)'],
    ['macd', 'MACD'],
    ['bollinger_bands', 'Bollinger Bands'],
    ['atr', 'Average True Range (ATR)'],
    ['relative_volume', 'Relative Volume (RVOL)'],
    ['average_dollar_volume', 'Average Dollar Volume'],
    ['historical_volatility', 'Historical Volatility'],
    ['prior_high', 'Price vs Prior High'],
  ];
  const LABELS = Object.fromEntries(INDUSTRY);
  const staticByFeature = new Map(catalog.map((item) => [item.feature_name, item]));
  const BINARY = new Set([
    'ma_cross_up', 'ma_cross_down', 'bb_upper_reached', 'bb_lower_reached',
    'bb_upper_cross_up', 'bb_lower_cross_down', 'bb_middle_cross_up', 'bb_middle_cross_down',
    'macd_cross_up', 'macd_cross_down', 'prior_high_breakout',
  ]);

  const METRICS = {
    moving_average: [
      ['ma_above', 'Price is above moving average'],
      ['ma_below', 'Price is below moving average'],
      ['ma_cross_up', 'Price crosses above moving average'],
      ['ma_cross_down', 'Price crosses below moving average'],
      ['ma_distance_pct', 'Price distance from moving average (%)'],
    ],
    price_roc: [['roc_pct', 'Price Rate of Change (ROC)']],
    rsi: [['rsi_value', 'RSI value']],
    macd: [
      ['macd_line_pct', 'MACD line'],
      ['macd_signal_pct', 'MACD signal line'],
      ['macd_histogram_pct', 'MACD histogram'],
      ['macd_cross_up', 'MACD crosses above signal'],
      ['macd_cross_down', 'MACD crosses below signal'],
    ],
    bollinger_bands: [
      ['bb_upper_reached', 'Price touches / exceeds upper band'],
      ['bb_lower_reached', 'Price touches / falls below lower band'],
      ['bb_upper_cross_up', 'Price crosses above upper band'],
      ['bb_lower_cross_down', 'Price crosses below lower band'],
      ['bb_middle_cross_up', 'Price crosses above middle band'],
      ['bb_middle_cross_down', 'Price crosses below middle band'],
      ['bb_upper_distance_pct', 'Price distance from upper band (%)'],
      ['bb_middle_distance_pct', 'Price distance from middle band (%)'],
      ['bb_lower_distance_pct', 'Price distance from lower band (%)'],
      ['bb_bandwidth_pct', 'Bollinger BandWidth (%)'],
      ['bb_position', 'Position within Bollinger Bands'],
    ],
    atr: [['atr_pct', 'ATR as % of price']],
    relative_volume: [['rvol', 'Relative Volume (RVOL)']],
    average_dollar_volume: [['average_dollar_volume', 'Average Dollar Volume']],
    historical_volatility: [['historical_volatility_pct', 'Annualized Historical Volatility (%)']],
    prior_high: [
      ['prior_high_breakout', 'Close is above prior high'],
      ['prior_high_distance_pct', 'Distance from prior high (%)'],
    ],
  };

  function option(value, label, selected = false) {
    const node = document.createElement('option');
    node.value = value; node.textContent = label; node.selected = selected;
    return node;
  }
  function numberToken(value) {
    return Number(value).toFixed(8).replace(/0+$/, '').replace(/\.$/, '').replaceAll('-', 'm').replaceAll('.', 'p');
  }
  function decodeNumber(value) { return Number(value.replaceAll('m', '-').replaceAll('p', '.')); }

  function parsedParameterized(featureName, rule = null) {
    if (!featureName || !featureName.startsWith('pi__')) return null;
    const parts = featureName.split('__');
    if (parts.length !== 6) return null;
    const family = parts[1], actualMetric = parts[2], source = parts[3];
    const period = Number(parts[4].slice(1));
    if (!LABELS[family] || !Number.isInteger(period)) return null;
    let metric = actualMetric;
    if (family === 'moving_average' && actualMetric === 'ma_distance_pct' && rule) {
      if (rule.operator === '>' && Number(rule.value) === 0) metric = 'ma_above';
      else if (rule.operator === '<' && Number(rule.value) === 0) metric = 'ma_below';
    }
    const parsed = {family, indicator: family, metric, actualMetric, source, period};
    if (family === 'moving_average') parsed.maType = parts[5];
    if (family === 'bollinger_bands') parsed.deviations = decodeNumber(parts[5].slice(1));
    if (family === 'macd') {
      const match = /^f(\d+)s(\d+)g(\d+)$/.exec(parts[5]);
      if (match) { parsed.fast = Number(match[1]); parsed.slow = Number(match[2]); parsed.signal = Number(match[3]); }
    }
    return parsed;
  }

  function sliderPair(label, cls, value, min, max, step) {
    const box = document.createElement('label');
    box.innerHTML = `${label}<div class="parameter-pair"><input class="${cls}" type="number" min="${min}" max="${max}" step="${step}" value="${value}"><input class="${cls}-slider" type="range" min="${min}" max="${max}" step="${step}" value="${value}"></div>`;
    const number = box.querySelector(`.${cls}`), slider = box.querySelector(`.${cls}-slider`);
    number.addEventListener('input', () => slider.value = number.value);
    slider.addEventListener('input', () => number.value = slider.value);
    return box;
  }

  function periodControl(parsed, family) {
    const defaultPeriod = family === 'moving_average' ? 200 : family === 'rsi' || family === 'atr' ? 14 : 20;
    const wrapper = sliderPair('Lookback / period (daily trading days)', 'param-period', parsed?.period ?? defaultPeriod, 2, 1000, 1);
    const quick = document.createElement('div'); quick.className = 'quick-periods';
    for (const value of [20, 50, 100, 200]) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = String(value);
      button.addEventListener('click', () => {
        wrapper.querySelector('.param-period').value = value;
        wrapper.querySelector('.param-period-slider').value = value;
      });
      quick.append(button);
    }
    wrapper.append(quick);
    return wrapper;
  }

  function parameterControls(row, parsed = null) {
    const family = row.querySelector('.rule-indicator').value;
    const meta = row.querySelector('.rule-meta'); meta.replaceChildren();
    const controls = document.createElement('div'); controls.className = 'indicator-parameters';
    const timeframe = document.createElement('div'); timeframe.className = 'parameter-note'; timeframe.textContent = 'Timeframe: Daily';
    controls.append(periodControl(parsed, family));

    if (!['relative_volume', 'average_dollar_volume', 'atr', 'historical_volatility'].includes(family)) {
      const sourceLabel = document.createElement('label');
      sourceLabel.innerHTML = 'Price source<select class="param-source"><option value="close">Close</option><option value="open">Open</option><option value="high">High</option><option value="low">Low</option></select>';
      sourceLabel.querySelector('select').value = parsed?.source || 'close'; controls.append(sourceLabel);
    } else {
      const source = document.createElement('input'); source.type = 'hidden'; source.className = 'param-source'; source.value = 'close'; controls.append(source);
    }

    if (family === 'moving_average') {
      const type = document.createElement('label');
      type.innerHTML = 'Average type<select class="param-ma-type"><option value="sma">Simple Moving Average (SMA)</option><option value="ema">Exponential Moving Average (EMA)</option></select>';
      type.querySelector('select').value = parsed?.maType || 'sma'; controls.append(type);
    } else if (family === 'bollinger_bands') {
      controls.append(sliderPair('Standard deviations', 'param-deviations', parsed?.deviations ?? 2, 0.01, 20, 0.01));
    } else if (family === 'macd') {
      const periodBox = controls.querySelector('label'); periodBox.hidden = true;
      controls.append(sliderPair('Fast EMA', 'param-fast', parsed?.fast ?? 12, 2, 200, 1));
      controls.append(sliderPair('Slow EMA', 'param-slow', parsed?.slow ?? 26, 3, 400, 1));
      controls.append(sliderPair('Signal EMA', 'param-signal', parsed?.signal ?? 9, 2, 200, 1));
    }
    controls.append(timeframe); meta.append(controls);
  }

  function fillMetrics(row, selectedFeature = null, rule = null) {
    const family = row.querySelector('.rule-indicator').value;
    const parsed = parsedParameterized(selectedFeature, rule);
    const metric = row.querySelector('.rule-metric'); metric.replaceChildren();
    for (const [value, label] of METRICS[family] || []) metric.append(option(value, label, parsed?.metric === value));
    parameterControls(row, parsed); applyThreshold(row, true, rule);
  }

  function thresholdSpec(family, metric) {
    if (BINARY.has(metric) || ['ma_above', 'ma_below'].includes(metric)) return {min: 0, max: 1, step: 1, value: 1, op: '==', fixed: true};
    if (family === 'rsi') return {min: 0, max: 100, step: 0.1, value: 50, op: '<=', unit: 'RSI points'};
    if (family === 'relative_volume') return {min: 0, max: 20, step: 0.05, value: 1.5, op: '>=', unit: '× average volume'};
    if (family === 'average_dollar_volume') return {min: 0, max: 100000000000, step: 1000000, value: 10000000, op: '>=', unit: '$ / day'};
    if (family === 'historical_volatility') return {min: 0, max: 500, step: 0.5, value: 50, op: '<=', unit: '% annualized'};
    if (family === 'atr') return {min: 0, max: 100, step: 0.1, value: 5, op: '<=', unit: '% of price'};
    if (metric === 'bb_position') return {min: -2, max: 3, step: 0.01, value: 1, op: '>=', unit: '0=lower, 1=upper'};
    return {min: -100, max: 500, step: 0.1, value: 0, op: '>', unit: '%'};
  }

  function applyThreshold(row, force = true, preserved = null) {
    const family = row.querySelector('.rule-indicator').value, metric = row.querySelector('.rule-metric').value;
    const spec = thresholdSpec(family, metric), op = row.querySelector('.rule-operator');
    const value = row.querySelector('.rule-value'), slider = row.querySelector('.rule-slider');
    const thresholdLabel = row.querySelector('.threshold-label'), sliderLabel = row.querySelector('.slider-wrap');
    Object.assign(value, {min: spec.min, max: spec.max, step: spec.step});
    Object.assign(slider, {min: spec.min, max: spec.max, step: spec.step});
    if (metric === 'ma_above') { op.value = '>'; value.value = 0; }
    else if (metric === 'ma_below') { op.value = '<'; value.value = 0; }
    else if (force && preserved) { op.value = preserved.operator; value.value = preserved.value; }
    else if (force) { op.value = spec.op; value.value = spec.value; }
    slider.value = value.value;
    thresholdLabel.hidden = Boolean(spec.fixed); sliderLabel.hidden = Boolean(spec.fixed); op.disabled = Boolean(spec.fixed);
    if (!spec.fixed) op.disabled = false;
    row.querySelector('.threshold-unit').textContent = spec.fixed ? 'Trigger condition; no numeric threshold required.' : spec.unit || '';
  }

  function ruleRow(rule = null) {
    const parsed = parsedParameterized(rule?.feature_name, rule);
    const legacy = staticByFeature.get(rule?.feature_name);
    const family = parsed?.family || 'moving_average';
    const row = document.createElement('div'); row.className = 'composer-row rule-row';
    row.innerHTML = `
      <label>Join<select class="rule-join"><option value="and">AND</option><option value="or">OR</option></select></label>
      <label>Indicator<select class="rule-indicator"></select></label>
      <label>Condition / output<select class="rule-metric"></select></label>
      <label>Comparison<select class="rule-operator"><option value=">">Above / greater than</option><option value=">=">At or above</option><option value="<">Below / less than</option><option value="<=">At or below</option><option value="==">Equals</option><option value="!=">Does not equal</option></select></label>
      <label class="threshold-label">Value<input class="rule-value" type="number"></label>
      <label class="slider-wrap">Value slider<input class="rule-slider" type="range"></label>
      <button class="remove-row" type="button">Remove</button>
      <div class="threshold-unit"></div><div class="rule-meta"></div>`;
    const indicator = row.querySelector('.rule-indicator');
    for (const [value, label] of INDUSTRY) indicator.append(option(value, label, value === family));
    if (legacy && !parsed) {
      indicator.append(option('legacy_fixed', `Legacy fixed metric — ${legacy.indicator_label}`, true));
      METRICS.legacy_fixed = [[legacy.feature_name, `${legacy.metric_label} (fixed parameters)`]];
    }
    row.querySelector('.rule-join').value = rule?.join || 'and';
    fillMetrics(row, rule?.feature_name || null, rule);
    indicator.addEventListener('change', () => fillMetrics(row, null, null));
    row.querySelector('.rule-metric').addEventListener('change', () => applyThreshold(row, true, null));
    row.querySelector('.rule-value').addEventListener('input', () => row.querySelector('.rule-slider').value = row.querySelector('.rule-value').value);
    row.querySelector('.rule-slider').addEventListener('input', () => row.querySelector('.rule-value').value = row.querySelector('.rule-slider').value);
    row.querySelector('.remove-row').addEventListener('click', () => { row.remove(); normalizeFirstRule(); });
    return row;
  }

  function normalizeFirstRule() {
    [...rules.querySelectorAll('.rule-row')].forEach((row, index) => {
      const join = row.querySelector('.rule-join'); join.disabled = index === 0; if (index === 0) join.value = 'and';
    });
  }
  function addRule(rule = null) { rules.append(ruleRow(rule)); normalizeFirstRule(); }

  function actualMetric(family, metric) {
    if (metric === 'ma_above' || metric === 'ma_below') return 'ma_distance_pct';
    return metric;
  }
  function featureName(row) {
    const family = row.querySelector('.rule-indicator').value;
    if (family === 'legacy_fixed') return row.querySelector('.rule-metric').value;
    const metric = actualMetric(family, row.querySelector('.rule-metric').value);
    const source = row.querySelector('.param-source')?.value || 'close';
    let period = Number(row.querySelector('.param-period')?.value || 20), suffix = 'standard';
    if (family === 'moving_average') suffix = row.querySelector('.param-ma-type').value;
    else if (family === 'bollinger_bands') suffix = `k${numberToken(Number(row.querySelector('.param-deviations').value))}`;
    else if (family === 'macd') {
      const fast = Number(row.querySelector('.param-fast').value), slow = Number(row.querySelector('.param-slow').value), signal = Number(row.querySelector('.param-signal').value);
      if (!(fast >= 2 && fast < slow && slow <= 400 && signal >= 2)) throw new Error('MACD requires fast EMA < slow EMA, with valid positive periods.');
      period = slow; suffix = `f${fast}s${slow}g${signal}`;
    } else if (family === 'rsi' || family === 'atr') suffix = 'wilder';
    else if (family === 'historical_volatility') suffix = 'annual252';
    else if (['relative_volume', 'average_dollar_volume', 'prior_high'].includes(family)) suffix = 'prior';
    if (!Number.isInteger(period) || period < 2 || period > 1000) throw new Error('Indicator period must be 2 to 1000 daily trading days.');
    return `pi__${family}__${metric}__${source}__p${period}__${suffix}`;
  }

  const stopBounds = (family) => (family === 'fixed' || family === 'trailing')
    ? {min: 0.01, max: 99.99, step: 0.01, unit: '%'} : {min: 0.01, max: 20, step: 0.01, unit: '× ATR'};
  function stopRow(stop = null) {
    const row = document.createElement('div'); row.className = 'composer-row stop-row';
    row.innerHTML = '<label>Exit type<select class="stop-family"><option value="fixed">Fixed % stop</option><option value="trailing">Trailing % stop</option><option value="atr">ATR stop</option><option value="trailing_atr">Trailing ATR stop</option></select></label><label>Exact value<input class="stop-value" type="number"></label><label class="slider-wrap">Slider<input class="stop-slider" type="range"></label><div class="stop-unit"></div><button class="remove-row" type="button">Remove</button>';
    const family = row.querySelector('.stop-family'), value = row.querySelector('.stop-value'), slider = row.querySelector('.stop-slider'), unit = row.querySelector('.stop-unit');
    family.value = stop?.family || 'fixed'; value.value = stop?.value || 5;
    function bounds() {
      const spec = stopBounds(family.value); Object.assign(value, {min: spec.min, max: spec.max, step: spec.step}); Object.assign(slider, {min: spec.min, max: spec.max, step: spec.step});
      let numeric = Number(value.value); if (!Number.isFinite(numeric) || numeric < spec.min || numeric > spec.max) numeric = family.value.includes('atr') ? 2 : 5;
      value.value = numeric; slider.value = numeric; unit.textContent = `${spec.unit} · ${spec.min} to ${spec.max}`;
    }
    family.addEventListener('change', bounds); value.addEventListener('input', () => slider.value = value.value); slider.addEventListener('input', () => value.value = slider.value); row.querySelector('.remove-row').addEventListener('click', () => row.remove()); bounds(); return row;
  }

  function hidden(name, value) { const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value; input.dataset.gen = '1'; form.append(input); }
  function compileRule(row, index) {
    const uiMetric = row.querySelector('.rule-metric').value;
    let operator = row.querySelector('.rule-operator').value, value = Number(row.querySelector('.rule-value').value);
    if (uiMetric === 'ma_above') { operator = '>'; value = 0; }
    else if (uiMetric === 'ma_below') { operator = '<'; value = 0; }
    else if (BINARY.has(uiMetric)) { operator = '=='; value = 1; }
    if (!Number.isFinite(value)) throw new Error('Every numeric condition needs a finite value.');
    return {feature: featureName(row), operator, value, join: index === 0 ? 'and' : row.querySelector('.rule-join').value};
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
        for (const rule of built) { hidden('rule_feature', rule.feature); hidden('rule_operator', rule.operator); hidden('rule_value', String(rule.value)); hidden('rule_join', rule.join); }
      } else {
        const expression = $('advanced-expression').value.trim(); if (!expression) throw new Error('Advanced expression cannot be empty.'); hidden('expression', expression);
      }
      const grouped = {fixed: [], trailing: [], atr: [], trailing_atr: []};
      for (const row of stops.querySelectorAll('.stop-row')) {
        const family = row.querySelector('.stop-family').value, value = Number(row.querySelector('.stop-value').value), spec = stopBounds(family);
        if (!Number.isFinite(value) || value < spec.min || value > spec.max) throw new Error(`Exit value must be ${spec.min} to ${spec.max}.`); grouped[family].push(value);
      }
      hidden('fixed_stops', grouped.fixed.join(',')); hidden('trailing_stops', grouped.trailing.join(',')); hidden('atr_stops', grouped.atr.join(',')); hidden('trailing_atr', grouped.trailing_atr.join(','));
    } catch (error) { event.preventDefault(); $('composer-error').hidden = false; $('composer-error').textContent = error.message || String(error); }
  });

  if (rules0.length) rules0.forEach(addRule);
  else addRule();
  stops0.forEach((stop) => stops.append(stopRow(stop)));
  function syncMode() { $('visual-builder-panel').hidden = !$('entry-mode-visual').checked; $('advanced-builder-panel').hidden = !$('entry-mode-advanced').checked; }
  $('entry-mode-visual').addEventListener('change', syncMode); $('entry-mode-advanced').addEventListener('change', syncMode); syncMode();
})();
"""

__all__ = ["STRATEGY_BUILDER_JS"]
