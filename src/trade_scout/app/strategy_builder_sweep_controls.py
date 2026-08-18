# ruff: noqa: E501
"""Presentation-only selectable result metrics for managed-exit sweeps."""

STRATEGY_BUILDER_SWEEP_CONTROLS_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;
  const variable = document.getElementById('sweep-variable');
  const resultCard = document.getElementById('strategy-sweep-results');
  if (!variable || !resultCard) return;

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
  const tableHeaders = [...sweepTable.querySelectorAll('thead th')].map((node) => node.textContent.trim());
  const tableIndex = Object.fromEntries(tableHeaders.map((name, position) => [name, position]));
  const parameterLabel = tableHeaders[0];
  const points = [...sweepTable.querySelectorAll('tbody tr')].map((row) => ({
    parameter: parse(row.cells[0]?.textContent),
    n: parse(row.cells[tableIndex.N]?.textContent),
    expectancy: parse(row.cells[tableIndex.Expectancy]?.textContent),
    delta: parse(row.cells[tableIndex['Delta vs hold']]?.textContent),
    stopOut: parse(row.cells[tableIndex['Stop-out']]?.textContent),
    targetHit: parse(row.cells[tableIndex['Target-hit']]?.textContent),
    p05: parse(row.cells[tableIndex.P05]?.textContent),
  })).filter((point) => point.parameter !== null);
  if (!points.length) return;

  const headers = [...originalTable.querySelectorAll('thead th')].map((node) => node.textContent.trim());
  const index = Object.fromEntries(headers.map((name, position) => [name, position]));
  const hold = [...originalTable.querySelectorAll('tbody tr')].find(
    (row) => row.cells[0]?.textContent?.trim().startsWith('Hold to maximum period')
  );
  const holdValue = (name) => hold && index[name] !== undefined ? parse(hold.cells[index[name]]?.textContent) : null;

  const METRICS = {
    expectancy: {label:'Expectancy', unit:'% per trade', hold:holdValue('Expectancy')},
    delta: {label:'Delta vs hold', unit:'percentage points', hold:0},
    stopOut: {label:'Stop-out rate', unit:'% of trades', hold:0},
    targetHit: {label:'Target-hit rate', unit:'% of trades', hold:0},
    p05: {label:'P05 / 5th-percentile return', unit:'% return', hold:holdValue('P05')},
  };

  const note = resultCard.querySelector('.section-note');
  const toolbar = document.createElement('div'); toolbar.className = 'toolbar';
  toolbar.innerHTML = `<label style="min-width:260px">Primary chart metric<select id="sweep-primary-metric"></select></label><label style="min-width:260px">Optional second metric<select id="sweep-secondary-metric"><option value="">None</option></select></label><span class="subtle">Two metrics use separate left/right scales. The table remains the exact numeric evidence.</span>`;
  note?.insertAdjacentElement('afterend', toolbar);
  const primary = toolbar.querySelector('#sweep-primary-metric');
  const secondary = toolbar.querySelector('#sweep-secondary-metric');
  for (const [key, metric] of Object.entries(METRICS)) {
    primary.append(new Option(metric.label, key, key === 'expectancy', key === 'expectancy'));
    secondary.append(new Option(metric.label, key, false, false));
  }

  const oldSvg = resultCard.querySelector('svg');
  const chartHost = document.createElement('div'); chartHost.id = 'sweep-chart-host'; oldSvg?.replaceWith(chartHost);
  function extent(values) {
    const finite = values.filter((value) => Number.isFinite(value));
    let min = Math.min(...finite), max = Math.max(...finite);
    if (min === max) { min -= 1; max += 1; }
    const padding = Math.max(Math.abs(max - min) * 0.12, 0.05); return [min - padding, max + padding];
  }
  function renderChart() {
    const primaryKey = primary.value, secondaryKey = secondary.value;
    const primaryMeta = METRICS[primaryKey], secondaryMeta = secondaryKey ? METRICS[secondaryKey] : null;
    const usable = points.filter((point) => Number.isFinite(point[primaryKey]));
    if (!usable.length) { chartHost.innerHTML = '<div class="section-note">The selected metric is unavailable for this sweep.</div>'; return; }
    const width=920,height=320,left=72,right=secondaryMeta?72:28,top=30,bottom=58;
    const xMin=Math.min(...usable.map((point)=>point.parameter)),xMax=Math.max(...usable.map((point)=>point.parameter));
    const primaryValues=usable.map((point)=>point[primaryKey]); if(Number.isFinite(primaryMeta.hold))primaryValues.push(primaryMeta.hold);
    const [pMin,pMax]=extent(primaryValues);
    const secondaryUsable=secondaryMeta?usable.filter((point)=>Number.isFinite(point[secondaryKey])):[];
    const secondaryValues=secondaryUsable.map((point)=>point[secondaryKey]); if(secondaryMeta&&Number.isFinite(secondaryMeta.hold))secondaryValues.push(secondaryMeta.hold);
    const [sMin,sMax]=secondaryValues.length?extent(secondaryValues):[0,1];
    const x=(value)=>left+(xMax===xMin?0.5:(value-xMin)/(xMax-xMin))*(width-left-right);
    const yp=(value)=>top+(pMax-value)/(pMax-pMin)*(height-top-bottom);
    const ys=(value)=>top+(sMax-value)/(sMax-sMin)*(height-top-bottom);
    const pLine=usable.map((point)=>`${x(point.parameter).toFixed(1)},${yp(point[primaryKey]).toFixed(1)}`).join(' ');
    const sLine=secondaryUsable.map((point)=>`${x(point.parameter).toFixed(1)},${ys(point[secondaryKey]).toFixed(1)}`).join(' ');
    const pDots=usable.map((point)=>`<circle cx="${x(point.parameter).toFixed(1)}" cy="${yp(point[primaryKey]).toFixed(1)}" r="4.5" fill="#f1c84b"><title>${point.parameter}: ${primaryMeta.label} ${point[primaryKey].toFixed(2)} ${primaryMeta.unit}</title></circle>`).join('');
    const sDots=secondaryUsable.map((point)=>`<circle cx="${x(point.parameter).toFixed(1)}" cy="${ys(point[secondaryKey]).toFixed(1)}" r="4" fill="#7fc8ff"><title>${point.parameter}: ${secondaryMeta.label} ${point[secondaryKey].toFixed(2)} ${secondaryMeta.unit}</title></circle>`).join('');
    const pHold=Number.isFinite(primaryMeta.hold)?`<line x1="${left}" x2="${width-right}" y1="${yp(primaryMeta.hold).toFixed(1)}" y2="${yp(primaryMeta.hold).toFixed(1)}" stroke="#98a6b8" stroke-dasharray="6 5"/>`:'';
    chartHost.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${primaryMeta.label} across ${parameterLabel} sweep" style="width:100%;min-height:280px;background:#10151d;border:1px solid #293241;border-radius:10px"><line x1="${left}" x2="${left}" y1="${top}" y2="${height-bottom}" stroke="#657184"/><line x1="${left}" x2="${width-right}" y1="${height-bottom}" y2="${height-bottom}" stroke="#657184"/>${pHold}<polyline points="${pLine}" fill="none" stroke="#f1c84b" stroke-width="3"/>${pDots}${secondaryMeta?`<polyline points="${sLine}" fill="none" stroke="#7fc8ff" stroke-width="2.5"/>${sDots}`:''}<text transform="translate(18 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle" fill="#f1c84b" font-size="12">${primaryMeta.label} · ${primaryMeta.unit}</text>${secondaryMeta?`<text transform="translate(${width-14} ${(top+height-bottom)/2}) rotate(90)" text-anchor="middle" fill="#7fc8ff" font-size="12">${secondaryMeta.label} · ${secondaryMeta.unit}</text>`:''}<text x="${left}" y="${height-20}" fill="#98a6b8" font-size="11">${xMin}</text><text x="${width-right}" y="${height-20}" text-anchor="end" fill="#98a6b8" font-size="11">${xMax}</text></svg>`;
  }
  primary.addEventListener('change', renderChart); secondary.addEventListener('change', renderChart); renderChart();
})();
"""

__all__ = ["STRATEGY_BUILDER_SWEEP_CONTROLS_JS"]
