# ruff: noqa: E501
"""Presentation-only compact sweep binding and selectable result metrics."""

STRATEGY_BUILDER_SWEEP_CONTROLS_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;

  const variable = document.getElementById('sweep-variable');
  const stops = document.getElementById('stop-rows');
  if (!variable || !stops) return;

  const FAMILY = {
    fixed: {label: 'Fixed stop distance', unit: '%'},
    trailing: {label: 'Trailing stop distance', unit: '%'},
    atr: {label: 'ATR stop multiple', unit: 'x ATR'},
    trailing_atr: {label: 'Trailing ATR multiple', unit: 'x ATR'},
  };

  function matchingRows() {
    const family = variable.value;
    if (!family) return [];
    return [...stops.querySelectorAll('.stop-row')].filter(
      (row) => row.querySelector('.stop-family')?.value === family
    );
  }

  function syncBoundRows() {
    const family = variable.value;
    for (const row of stops.querySelectorAll('.stop-row')) {
      if (row.dataset.sweepDisplayLocked === '1') {
        row.style.removeProperty('display');
        row.removeAttribute('aria-hidden');
        delete row.dataset.sweepDisplayLocked;
      }
    }
    if (!family || !FAMILY[family]) return;
    for (const row of matchingRows()) {
      row.dataset.sweepDisplayLocked = '1';
      row.style.setProperty('display', 'none', 'important');
      row.setAttribute('aria-hidden', 'true');
    }
    const notice = document.getElementById('sweep-bound-notice');
    const from = document.getElementById('sweep-from')?.value;
    const to = document.getElementById('sweep-to')?.value;
    const step = document.getElementById('sweep-step')?.value;
    if (notice && from && to && step) {
      notice.dataset.compactSweep = '1';
      const button = notice.querySelector('#sweep-use-single')?.outerHTML || '';
      notice.innerHTML = `<strong>${FAMILY[family].label} is controlled by Section 5</strong> · ${from}${FAMILY[family].unit} → ${to}${FAMILY[family].unit}, step ${step}${FAMILY[family].unit}. The repeated single-value exit rows are hidden. ${button}`;
      notice.querySelector('#sweep-use-single')?.addEventListener('click', () => queueMicrotask(syncBoundRows));
    }
  }

  variable.addEventListener('change', () => queueMicrotask(syncBoundRows));
  for (const id of ['sweep-from', 'sweep-to', 'sweep-step']) {
    document.getElementById(id)?.addEventListener('input', () => queueMicrotask(syncBoundRows));
  }
  new MutationObserver(() => queueMicrotask(syncBoundRows)).observe(stops, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['hidden'],
  });
  queueMicrotask(syncBoundRows);

  const resultCard = document.getElementById('strategy-sweep-results');
  if (!resultCard) return;
  const sweepTable = resultCard.querySelector('table');
  const originalTable = [...document.querySelectorAll('table')].find(
    (node) => node.closest('.card')?.querySelector('h2')?.textContent?.trim() ===
      'Exit comparison on frozen entry population'
  );
  if (!sweepTable || !originalTable) return;

  const parse = (text) => {
    const number = Number(String(text || '').replaceAll(',', '').replace('%', '').replace('+', '').trim());
    return Number.isFinite(number) ? number : null;
  };
  const headers = [...originalTable.querySelectorAll('thead th')].map((node) => node.textContent.trim());
  const index = Object.fromEntries(headers.map((name, position) => [name, position]));
  const hold = [...originalTable.querySelectorAll('tbody tr')].find(
    (row) => row.cells[0]?.textContent?.trim().startsWith('Hold to maximum holding period')
  );
  const holdValue = (name) => hold && index[name] !== undefined ? parse(hold.cells[index[name]]?.textContent) : null;

  const tableHeaders = [...sweepTable.querySelectorAll('thead th')].map((node) => node.textContent.trim());
  const tableIndex = Object.fromEntries(tableHeaders.map((name, position) => [name, position]));
  const parameterLabel = tableHeaders[0];
  const points = [...sweepTable.querySelectorAll('tbody tr')].map((row) => ({
    parameter: parse(row.cells[0]?.textContent),
    n: parse(row.cells[tableIndex.N]?.textContent),
    expectancy: parse(row.cells[tableIndex.Expectancy]?.textContent),
    delta: parse(row.cells[tableIndex['Delta vs hold']]?.textContent),
    stopOut: parse(row.cells[tableIndex['Stop-out']]?.textContent),
    p05: parse(row.cells[tableIndex.P05]?.textContent),
  })).filter((point) => point.parameter !== null);

  const originalRows = [...originalTable.querySelectorAll('tbody tr')].filter(
    (row) => !row.cells[0]?.textContent?.trim().startsWith('Hold to maximum holding period')
  );
  for (let i = 0; i < points.length && i < originalRows.length; i += 1) {
    points[i].winRate = index['Win rate'] === undefined ? null : parse(originalRows[i].cells[index['Win rate']]?.textContent);
    points[i].profitFactor = index.PF === undefined ? null : parse(originalRows[i].cells[index.PF]?.textContent);
    points[i].avgHold = index['Avg hold'] === undefined ? null : parse(originalRows[i].cells[index['Avg hold']]?.textContent);
  }

  const METRICS = {
    expectancy: {label: 'Expectancy', unit: '% per trade', hold: holdValue('Expectancy')},
    delta: {label: 'Delta vs hold', unit: 'percentage points', hold: 0},
    stopOut: {label: 'Stop-out rate', unit: '% of trades', hold: 0},
    p05: {label: 'P05 / 5th-percentile return', unit: '% return', hold: holdValue('P05')},
    winRate: {label: 'Win rate', unit: '% of trades', hold: holdValue('Win rate')},
    profitFactor: {label: 'Profit factor', unit: 'ratio', hold: holdValue('PF')},
    avgHold: {label: 'Average holding period', unit: 'sessions', hold: holdValue('Avg hold')},
  };

  const note = resultCard.querySelector('.section-note');
  const toolbar = document.createElement('div');
  toolbar.className = 'toolbar';
  toolbar.innerHTML = `
    <label style="min-width:260px">Primary chart metric<select id="sweep-primary-metric"></select></label>
    <label style="min-width:260px">Optional second metric<select id="sweep-secondary-metric"><option value="">None</option></select></label>
    <span class="subtle">Two metrics use separate left/right scales. Read the labels; color is not the evidence.</span>`;
  note?.insertAdjacentElement('afterend', toolbar);
  const primary = toolbar.querySelector('#sweep-primary-metric');
  const secondary = toolbar.querySelector('#sweep-secondary-metric');
  for (const [key, metric] of Object.entries(METRICS)) {
    primary.append(new Option(metric.label, key, key === 'expectancy', key === 'expectancy'));
    secondary.append(new Option(metric.label, key, key === 'p05', key === 'p05'));
  }

  const oldSvg = resultCard.querySelector('svg');
  const chartHost = document.createElement('div');
  chartHost.id = 'sweep-chart-host';
  oldSvg?.replaceWith(chartHost);

  function extent(values) {
    const finite = values.filter((value) => Number.isFinite(value));
    let min = Math.min(...finite), max = Math.max(...finite);
    if (min === max) { min -= 1; max += 1; }
    const padding = Math.max(Math.abs(max - min) * 0.12, 0.05);
    return [min - padding, max + padding];
  }

  function renderChart() {
    const primaryKey = primary.value;
    const secondaryKey = secondary.value;
    const primaryMeta = METRICS[primaryKey];
    const secondaryMeta = secondaryKey ? METRICS[secondaryKey] : null;
    const usable = points.filter((point) => Number.isFinite(point[primaryKey]));
    if (!usable.length) {
      chartHost.innerHTML = '<div class="section-note">The selected metric is unavailable for this sweep.</div>';
      return;
    }
    const width = 920, height = 320, left = 72, right = secondaryMeta ? 72 : 28, top = 30, bottom = 58;
    const xMin = Math.min(...usable.map((point) => point.parameter));
    const xMax = Math.max(...usable.map((point) => point.parameter));
    const primaryValues = usable.map((point) => point[primaryKey]);
    if (Number.isFinite(primaryMeta.hold)) primaryValues.push(primaryMeta.hold);
    const [pMin, pMax] = extent(primaryValues);
    const secondaryValues = secondaryMeta
      ? usable.map((point) => point[secondaryKey]).filter((value) => Number.isFinite(value))
      : [];
    if (secondaryMeta && Number.isFinite(secondaryMeta.hold)) secondaryValues.push(secondaryMeta.hold);
    const [sMin, sMax] = secondaryValues.length ? extent(secondaryValues) : [0, 1];
    const x = (value) => left + (xMax === xMin ? 0.5 : (value - xMin) / (xMax - xMin)) * (width - left - right);
    const yPrimary = (value) => top + (pMax - value) / (pMax - pMin) * (height - top - bottom);
    const ySecondary = (value) => top + (sMax - value) / (sMax - sMin) * (height - top - bottom);
    const primaryLine = usable.map((point) => `${x(point.parameter).toFixed(1)},${yPrimary(point[primaryKey]).toFixed(1)}`).join(' ');
    const secondaryUsable = secondaryMeta ? usable.filter((point) => Number.isFinite(point[secondaryKey])) : [];
    const secondaryLine = secondaryUsable.map((point) => `${x(point.parameter).toFixed(1)},${ySecondary(point[secondaryKey]).toFixed(1)}`).join(' ');
    const primaryCircles = usable.map((point) => `<circle cx="${x(point.parameter).toFixed(1)}" cy="${yPrimary(point[primaryKey]).toFixed(1)}" r="4.5" fill="#f1c84b"><title>${point.parameter}: ${primaryMeta.label} ${point[primaryKey].toFixed(2)} ${primaryMeta.unit}</title></circle>`).join('');
    const secondaryCircles = secondaryUsable.map((point) => `<circle cx="${x(point.parameter).toFixed(1)}" cy="${ySecondary(point[secondaryKey]).toFixed(1)}" r="4" fill="#7fc8ff"><title>${point.parameter}: ${secondaryMeta.label} ${point[secondaryKey].toFixed(2)} ${secondaryMeta.unit}</title></circle>`).join('');
    const primaryHold = Number.isFinite(primaryMeta.hold)
      ? `<line x1="${left}" x2="${width - right}" y1="${yPrimary(primaryMeta.hold).toFixed(1)}" y2="${yPrimary(primaryMeta.hold).toFixed(1)}" stroke="#98a6b8" stroke-dasharray="6 5"/><text x="${width - right}" y="${(yPrimary(primaryMeta.hold) - 5).toFixed(1)}" text-anchor="end" fill="#98a6b8" font-size="11">Hold ${primaryMeta.hold.toFixed(2)}</text>`
      : '';
    const secondaryHold = secondaryMeta && Number.isFinite(secondaryMeta.hold)
      ? `<line x1="${left}" x2="${width - right}" y1="${ySecondary(secondaryMeta.hold).toFixed(1)}" y2="${ySecondary(secondaryMeta.hold).toFixed(1)}" stroke="#7fc8ff" opacity=".45" stroke-dasharray="2 5"/>`
      : '';
    chartHost.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${primaryMeta.label} across ${parameterLabel} sweep" style="width:100%;min-height:280px;background:#10151d;border:1px solid #293241;border-radius:10px">
      <line x1="${left}" x2="${left}" y1="${top}" y2="${height - bottom}" stroke="#657184"/>
      <line x1="${left}" x2="${width - right}" y1="${height - bottom}" y2="${height - bottom}" stroke="#657184"/>
      ${primaryHold}${secondaryHold}
      <polyline points="${primaryLine}" fill="none" stroke="#f1c84b" stroke-width="3"/>${primaryCircles}
      ${secondaryMeta ? `<polyline points="${secondaryLine}" fill="none" stroke="#7fc8ff" stroke-width="2.5"/>${secondaryCircles}` : ''}
      <text x="${left}" y="${height - 20}" fill="#98a6b8" font-size="11">${xMin}</text>
      <text x="${width - right}" y="${height - 20}" text-anchor="end" fill="#98a6b8" font-size="11">${xMax}</text>
      <text x="${(left + width - right) / 2}" y="${height - 20}" text-anchor="middle" fill="#edf1f7" font-size="12">${parameterLabel}</text>
      <text transform="translate(18 ${(top + height - bottom) / 2}) rotate(-90)" text-anchor="middle" fill="#f1c84b" font-size="12">${primaryMeta.label} · ${primaryMeta.unit}</text>
      ${secondaryMeta ? `<text transform="translate(${width - 14} ${(top + height - bottom) / 2}) rotate(90)" text-anchor="middle" fill="#7fc8ff" font-size="12">${secondaryMeta.label} · ${secondaryMeta.unit}</text>` : ''}
      <text x="${left}" y="${top + 10}" fill="#f1c84b" font-size="11">Left: ${primaryMeta.label}</text>
      ${secondaryMeta ? `<text x="${left}" y="${top + 26}" fill="#7fc8ff" font-size="11">Right: ${secondaryMeta.label}</text>` : ''}
    </svg>`;
  }

  primary.addEventListener('change', renderChart);
  secondary.addEventListener('change', renderChart);
  renderChart();
})();
"""

__all__ = ["STRATEGY_BUILDER_SWEEP_CONTROLS_JS"]
