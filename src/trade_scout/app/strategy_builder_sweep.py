# ruff: noqa: E501
"""Presentation-only one-variable exit-policy sweep controls for Strategy Builder."""

STRATEGY_BUILDER_SWEEP_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;
  const form = document.getElementById('strategy-form');
  const stops = document.getElementById('stop-rows');
  if (!form || !stops || document.getElementById('strategy-sweep-card')) return;

  const META = {
    fixed: {
      label: 'Fixed stop distance (%)', field: 'fixed_stops', min: 0.01, max: 99.99,
      defaultFrom: 1, defaultTo: 10, defaultStep: 1, unit: '%',
    },
    trailing: {
      label: 'Trailing stop distance (%)', field: 'trailing_stops', min: 0.01, max: 99.99,
      defaultFrom: 1, defaultTo: 10, defaultStep: 1, unit: '%',
    },
    atr: {
      label: 'ATR stop multiple', field: 'atr_stops', min: 0.01, max: 20,
      defaultFrom: 0.5, defaultTo: 4, defaultStep: 0.5, unit: 'x ATR',
    },
    trailing_atr: {
      label: 'Trailing ATR multiple', field: 'trailing_atr', min: 0.01, max: 20,
      defaultFrom: 0.5, defaultTo: 4, defaultStep: 0.5, unit: 'x ATR',
    },
  };

  const executionCard = [...form.querySelectorAll(':scope > .card')].find(
    (node) => node.querySelector('h2')?.textContent?.trim() === '4. Execution assumptions'
  );
  if (!executionCard) return;

  const card = document.createElement('div');
  card.id = 'strategy-sweep-card'; card.className = 'card';
  card.innerHTML = `
    <h2>5. Research variable — one-variable sweep</h2>
    <div class="section-note"><strong>Purpose:</strong> test a complete range for one parameter while every other setting stays fixed. This first slice supports exit-policy parameters because they all use the same frozen entry population. Entry-indicator sweeps will be added separately because changing an entry parameter changes which events exist.</div>
    <div class="top-grid">
      <label>Variable under test<select id="sweep-variable" name="sweep_variable">
        <option value="">No sweep — use exact settings above</option>
        <option value="fixed">Fixed stop distance (%)</option>
        <option value="trailing">Trailing stop distance (%)</option>
        <option value="atr">ATR stop multiple</option>
        <option value="trailing_atr">Trailing ATR multiple</option>
      </select></label>
      <label>From<input id="sweep-from" name="sweep_from" type="number"></label>
      <label>To<input id="sweep-to" name="sweep_to" type="number"></label>
      <label>Step<input id="sweep-step" name="sweep_step" type="number"></label>
    </div>
    <div id="sweep-preview" class="section-note">No research variable selected. Your exact exit candidates above will be used.</div>`;
  executionCard.insertAdjacentElement('afterend', card);

  const runToolbar = executionCard.querySelector('.toolbar');
  if (runToolbar) card.append(runToolbar);

  const variable = document.getElementById('sweep-variable');
  const from = document.getElementById('sweep-from');
  const to = document.getElementById('sweep-to');
  const step = document.getElementById('sweep-step');
  const preview = document.getElementById('sweep-preview');
  const exitCard = stops.closest('.card');
  const boundNotice = document.createElement('div');
  boundNotice.id = 'sweep-bound-notice'; boundNotice.className = 'section-note'; boundNotice.hidden = true;
  exitCard?.querySelector('.section-note')?.insertAdjacentElement('afterend', boundNotice);

  const query = new URLSearchParams(window.location.search);
  const initialVariable = query.get('sweep_variable');
  if (initialVariable && META[initialVariable]) variable.value = initialVariable;

  let lastVariable = variable.value;

  function numericInput(node, meta, value) {
    node.min = String(meta.min); node.max = String(meta.max); node.step = '0.01';
    node.value = String(value);
  }

  function roundValue(value) {
    return Number(value.toFixed(8));
  }

  function valuesForCurrentSweep() {
    const meta = META[variable.value];
    if (!meta) return [];
    const start = Number(from.value), end = Number(to.value), increment = Number(step.value);
    if (![start, end, increment].every(Number.isFinite)) throw new Error('Sweep from, to and step must be numbers.');
    if (start < meta.min || start > meta.max || end < meta.min || end > meta.max) {
      throw new Error(`${meta.label} sweep must stay between ${meta.min} and ${meta.max}.`);
    }
    if (end < start) throw new Error('Sweep “To” must be greater than or equal to “From”.');
    if (increment <= 0) throw new Error('Sweep step must be greater than zero.');
    const values = [];
    for (let value = start; value <= end + increment * 1e-8; value += increment) {
      values.push(roundValue(value));
      if (values.length > 60) throw new Error('This first one-variable sweep is limited to 60 tested values. Increase the step size.');
    }
    if (!values.length) throw new Error('The selected sweep contains no values.');
    return values;
  }

  function familyRows(family) {
    return [...stops.querySelectorAll('.stop-row')].filter(
      (row) => row.querySelector('.stop-family')?.value === family
    );
  }

  function unlockAllRows() {
    for (const row of stops.querySelectorAll('.stop-row')) {
      if (row.dataset.sweepHidden === '1') row.hidden = false;
      delete row.dataset.sweepHidden;
    }
  }

  function collapseFamilyToSingle(family) {
    if (!family) return;
    const rows = familyRows(family);
    rows.slice(1).forEach((row) => row.remove());
    if (rows[0]) { rows[0].hidden = false; delete rows[0].dataset.sweepHidden; }
  }

  function lockBoundRows() {
    unlockAllRows();
    const family = variable.value;
    const meta = META[family];
    if (!meta) {
      boundNotice.hidden = true;
      return;
    }
    const rows = familyRows(family);
    for (const row of rows) { row.hidden = true; row.dataset.sweepHidden = '1'; }
    boundNotice.hidden = false;
    boundNotice.innerHTML = `<strong>Under test:</strong> ${meta.label}. Matching single-value rows are hidden because Section 5 controls this entire range. Other exit families stay fixed. <button id="sweep-use-single" type="button">Use one exact value instead</button>`;
    document.getElementById('sweep-use-single')?.addEventListener('click', () => {
      const familyToKeep = variable.value;
      variable.value = '';
      collapseFamilyToSingle(familyToKeep);
      lastVariable = '';
      refresh(false);
    });
  }

  function setDefaults(meta, restoreQuery) {
    const start = restoreQuery ? Number(query.get('sweep_from')) : NaN;
    const end = restoreQuery ? Number(query.get('sweep_to')) : NaN;
    const increment = restoreQuery ? Number(query.get('sweep_step')) : NaN;
    numericInput(from, meta, Number.isFinite(start) ? start : meta.defaultFrom);
    numericInput(to, meta, Number.isFinite(end) ? end : meta.defaultTo);
    numericInput(step, meta, Number.isFinite(increment) ? increment : meta.defaultStep);
  }

  function renderPreview() {
    const meta = META[variable.value];
    if (!meta) {
      from.disabled = true; to.disabled = true; step.disabled = true;
      preview.textContent = 'No research variable selected. Your exact exit candidates above will be used.';
      return;
    }
    from.disabled = false; to.disabled = false; step.disabled = false;
    try {
      const values = valuesForCurrentSweep();
      const display = values.length <= 14 ? values.join(', ') : `${values.slice(0, 6).join(', ')} … ${values.slice(-3).join(', ')}`;
      preview.innerHTML = `<strong>${values.length} predeclared values:</strong> ${display} ${meta.unit}. Every value will be retained in the result; SCOUT will not keep only the historical winner.`;
    } catch (error) {
      preview.innerHTML = `<strong>Fix sweep:</strong> ${error.message || String(error)}`;
    }
  }

  function refresh(restoreQuery = false) {
    const meta = META[variable.value];
    if (meta && (restoreQuery || variable.value !== lastVariable)) setDefaults(meta, restoreQuery);
    lockBoundRows(); renderPreview(); lastVariable = variable.value;
  }

  variable.addEventListener('change', () => {
    if (lastVariable && lastVariable !== variable.value) collapseFamilyToSingle(lastVariable);
    refresh(false);
  });
  from.addEventListener('input', renderPreview);
  to.addEventListener('input', renderPreview);
  step.addEventListener('input', renderPreview);

  form.addEventListener('submit', (event) => {
    if (event.defaultPrevented || !variable.value) return;
    try {
      const meta = META[variable.value];
      const values = valuesForCurrentSweep();
      form.querySelectorAll(`input[name="${meta.field}"][data-gen="1"],input[name="${meta.field}"][data-sweep-gen="1"]`).forEach((node) => node.remove());
      const hidden = document.createElement('input'); hidden.type = 'hidden'; hidden.name = meta.field;
      hidden.value = values.join(','); hidden.dataset.sweepGen = '1'; form.append(hidden);
    } catch (error) {
      event.preventDefault();
      const composerError = document.getElementById('composer-error');
      if (composerError) { composerError.hidden = false; composerError.textContent = error.message || String(error); }
    }
  });

  function parsePercent(text) {
    const value = Number(String(text).replace('%', '').replace('+', '').trim());
    return Number.isFinite(value) ? value : null;
  }

  function parameterFromLabel(label, family) {
    const patterns = {
      fixed: /^Fixed ([0-9.]+)% stop/,
      trailing: /^Trailing ([0-9.]+)% stop/,
      atr: /^ATR ([0-9.]+)x stop/,
      trailing_atr: /^Trailing ATR ([0-9.]+)x stop/,
    };
    const match = patterns[family]?.exec(label);
    return match ? Number(match[1]) : null;
  }

  function renderSweepResults() {
    const family = variable.value, meta = META[family];
    if (!meta) return;
    const table = [...document.querySelectorAll('table')].find(
      (node) => node.closest('.card')?.querySelector('h2')?.textContent?.trim() === 'Exit comparison on frozen entry population'
    );
    if (!table) return;
    const headers = [...table.querySelectorAll('thead th')].map((node) => node.textContent.trim());
    const byName = Object.fromEntries(headers.map((name, index) => [name, index]));
    const rows = [...table.querySelectorAll('tbody tr')];
    const holdRow = rows.find((row) => row.cells[0]?.textContent?.trim().startsWith('Hold to maximum holding period'));
    const holdExpectancy = holdRow ? parsePercent(holdRow.cells[byName.Expectancy]?.textContent) : null;
    const points = rows.map((row) => {
      const value = parameterFromLabel(row.cells[0]?.textContent?.trim() || '', family);
      if (value === null) return null;
      return {
        value,
        n: Number(row.cells[byName.N]?.textContent?.trim()),
        expectancy: parsePercent(row.cells[byName.Expectancy]?.textContent),
        delta: parsePercent(row.cells[byName['Delta vs hold']]?.textContent),
        stopOut: parsePercent(row.cells[byName['Stop-out']]?.textContent),
        p05: parsePercent(row.cells[byName.P05]?.textContent),
      };
    }).filter((item) => item && item.expectancy !== null).sort((a, b) => a.value - b.value);
    if (!points.length) return;

    const width = 900, height = 300, left = 62, right = 24, top = 26, bottom = 52;
    const xMin = points[0].value, xMax = points[points.length - 1].value;
    const yValues = points.map((point) => point.expectancy);
    if (holdExpectancy !== null) yValues.push(holdExpectancy);
    let yMin = Math.min(...yValues), yMax = Math.max(...yValues);
    const padding = Math.max(0.5, (yMax - yMin) * 0.15); yMin -= padding; yMax += padding;
    const x = (value) => left + (xMax === xMin ? 0.5 : (value - xMin) / (xMax - xMin)) * (width - left - right);
    const y = (value) => top + (yMax - value) / (yMax - yMin) * (height - top - bottom);
    const polyline = points.map((point) => `${x(point.value).toFixed(1)},${y(point.expectancy).toFixed(1)}`).join(' ');
    const circles = points.map((point) => `<circle cx="${x(point.value).toFixed(1)}" cy="${y(point.expectancy).toFixed(1)}" r="5" fill="#f1c84b"><title>${point.value}${meta.unit}: expectancy ${point.expectancy >= 0 ? '+' : ''}${point.expectancy.toFixed(2)}%, N=${point.n}</title></circle>`).join('');
    const holdLine = holdExpectancy === null ? '' : `<line x1="${left}" x2="${width - right}" y1="${y(holdExpectancy).toFixed(1)}" y2="${y(holdExpectancy).toFixed(1)}" stroke="#98a6b8" stroke-dasharray="6 5"/><text x="${width - right}" y="${(y(holdExpectancy) - 6).toFixed(1)}" text-anchor="end" fill="#98a6b8" font-size="12">Hold ${holdExpectancy >= 0 ? '+' : ''}${holdExpectancy.toFixed(2)}%</text>`;
    const best = points.reduce((winner, point) => point.expectancy > winner.expectancy ? point : winner);

    const resultCard = document.createElement('div');
    resultCard.id = 'strategy-sweep-results'; resultCard.className = 'card s12';
    resultCard.innerHTML = `<h2>One-variable sweep — ${meta.label}</h2>
      <div class="section-note"><strong>Read the shape, not just the peak.</strong> A broad region with similar results is more credible than one isolated historical maximum. The marked best value below is descriptive only, not a validated optimum.</div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Expectancy across ${meta.label} sweep" style="width:100%;min-height:260px;background:#10151d;border:1px solid #293241;border-radius:10px">
        <line x1="${left}" x2="${left}" y1="${top}" y2="${height - bottom}" stroke="#657184"/>
        <line x1="${left}" x2="${width - right}" y1="${height - bottom}" y2="${height - bottom}" stroke="#657184"/>
        ${holdLine}
        <polyline points="${polyline}" fill="none" stroke="#f1c84b" stroke-width="3"/>
        ${circles}
        <text x="${left}" y="${height - 18}" fill="#98a6b8" font-size="12">${xMin}${meta.unit}</text>
        <text x="${width - right}" y="${height - 18}" text-anchor="end" fill="#98a6b8" font-size="12">${xMax}${meta.unit}</text>
        <text x="14" y="${top + 8}" fill="#98a6b8" font-size="12">${yMax.toFixed(1)}%</text>
        <text x="14" y="${height - bottom}" fill="#98a6b8" font-size="12">${yMin.toFixed(1)}%</text>
        <text x="${(left + width - right) / 2}" y="${height - 18}" text-anchor="middle" fill="#edf1f7" font-size="13">${meta.label}</text>
        <text transform="translate(16 ${(top + height - bottom) / 2}) rotate(-90)" text-anchor="middle" fill="#edf1f7" font-size="13">Expectancy per trade</text>
      </svg>
      <p><strong>Best observed expectancy in this tested range:</strong> ${best.value}${meta.unit} → ${best.expectancy >= 0 ? '+' : ''}${best.expectancy.toFixed(2)}%. Treat this as a location to inspect, not a recommendation.</p>
      <div class="scroll"><table><thead><tr><th>${meta.label}</th><th>N</th><th>Expectancy</th><th>Delta vs hold</th><th>Stop-out</th><th>P05</th></tr></thead><tbody>${points.map((point) => `<tr><td>${point.value}${meta.unit}</td><td>${point.n}</td><td>${point.expectancy >= 0 ? '+' : ''}${point.expectancy.toFixed(2)}%</td><td>${point.delta === null ? '-' : `${point.delta >= 0 ? '+' : ''}${point.delta.toFixed(2)}%`}</td><td>${point.stopOut === null ? '-' : `${point.stopOut.toFixed(1)}%`}</td><td>${point.p05 === null ? '-' : `${point.p05 >= 0 ? '+' : ''}${point.p05.toFixed(2)}%`}</td></tr>`).join('')}</tbody></table></div>`;
    const plainReadout = document.getElementById('plain-english-readout');
    (plainReadout || table.closest('.card')).insertAdjacentElement(plainReadout ? 'afterend' : 'beforebegin', resultCard);
  }

  if (variable.value) {
    const meta = META[variable.value];
    setDefaults(meta, Boolean(initialVariable));
  }
  refresh(Boolean(initialVariable));
  renderSweepResults();
})();
"""

__all__ = ["STRATEGY_BUILDER_SWEEP_JS"]
