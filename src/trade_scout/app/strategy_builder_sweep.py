# ruff: noqa: E501
"""Presentation-only one-variable managed-exit sweep controls for Strategy Builder."""

STRATEGY_BUILDER_SWEEP_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;
  const form = document.getElementById('strategy-form');
  const exits = document.getElementById('exit-plan-rows');
  if (!form || !exits || document.getElementById('strategy-sweep-card')) return;

  const META = {
    fixed: {component:'stop', family:'fixed', label:'Fixed stop distance (%)', min:0.01, max:99.99, defaultFrom:1, defaultTo:10, defaultStep:1, unit:'%'},
    trailing: {component:'stop', family:'trailing', label:'Trailing stop distance (%)', min:0.01, max:99.99, defaultFrom:1, defaultTo:10, defaultStep:1, unit:'%'},
    atr: {component:'stop', family:'atr', label:'ATR stop multiple', min:0.01, max:20, defaultFrom:0.5, defaultTo:4, defaultStep:0.5, unit:'x ATR'},
    trailing_atr: {component:'stop', family:'trailing_atr', label:'Trailing ATR stop multiple', min:0.01, max:20, defaultFrom:0.5, defaultTo:4, defaultStep:0.5, unit:'x ATR'},
    target_fixed: {component:'target', family:'fixed', label:'Fixed profit target (%)', min:0.01, max:500, defaultFrom:5, defaultTo:30, defaultStep:5, unit:'%'},
    target_atr: {component:'target', family:'atr', label:'ATR profit target multiple', min:0.01, max:20, defaultFrom:1, defaultTo:5, defaultStep:0.5, unit:'x ATR'},
    target_r: {component:'target', family:'r', label:'Risk-multiple profit target', min:0.01, max:20, defaultFrom:1, defaultTo:5, defaultStep:0.5, unit:'R'},
  };

  const executionCard = [...form.querySelectorAll(':scope > .card')].find(
    (node) => node.querySelector('h2')?.textContent?.trim() === '4. Execution assumptions'
  );
  if (!executionCard) return;

  const card = document.createElement('div');
  card.id = 'strategy-sweep-card'; card.className = 'card';
  card.innerHTML = `
    <h2>5. Research variable — one-variable sweep</h2>
    <div class="section-note"><strong>Purpose:</strong> choose one stop or profit-target parameter to vary while every other part of that exit plan stays fixed. The matching plan is bound to this range so you do not accidentally change the same variable in two places.</div>
    <div class="top-grid">
      <label>Variable under test<select id="sweep-variable" name="sweep_variable">
        <option value="">No sweep — use exact exit plans above</option>
        <option value="fixed">Fixed stop distance (%)</option>
        <option value="trailing">Trailing stop distance (%)</option>
        <option value="atr">ATR stop multiple</option>
        <option value="trailing_atr">Trailing ATR stop multiple</option>
        <option value="target_fixed">Fixed profit target (%)</option>
        <option value="target_atr">ATR profit target multiple</option>
        <option value="target_r">Risk-multiple profit target</option>
      </select></label>
      <label>From<input id="sweep-from" name="sweep_from" type="number"></label>
      <label>To<input id="sweep-to" name="sweep_to" type="number"></label>
      <label>Step<input id="sweep-step" name="sweep_step" type="number"></label>
    </div>
    <div id="sweep-preview" class="section-note">No research variable selected. Your exact exit plans above will be used.</div>`;
  executionCard.insertAdjacentElement('afterend', card);
  const runToolbar = executionCard.querySelector('.toolbar');
  if (runToolbar) card.append(runToolbar);

  const variable = document.getElementById('sweep-variable');
  const from = document.getElementById('sweep-from');
  const to = document.getElementById('sweep-to');
  const step = document.getElementById('sweep-step');
  const preview = document.getElementById('sweep-preview');
  const exitCard = exits.closest('.card');
  const boundNotice = document.createElement('div');
  boundNotice.id = 'sweep-bound-notice'; boundNotice.className = 'section-note'; boundNotice.hidden = true;
  exitCard?.querySelector('.section-note')?.insertAdjacentElement('afterend', boundNotice);

  const query = new URLSearchParams(window.location.search);
  const initialVariable = query.get('sweep_variable');
  if (initialVariable && META[initialVariable]) variable.value = initialVariable;
  let lastVariable = variable.value;

  function numericInput(node, meta, value) {
    node.min = String(meta.min); node.max = String(meta.max); node.step = '0.01'; node.value = String(value);
  }
  function roundValue(value) { return Number(value.toFixed(8)); }
  function valuesForCurrentSweep() {
    const meta = META[variable.value];
    if (!meta) return [];
    const start = Number(from.value), end = Number(to.value), increment = Number(step.value);
    if (![start, end, increment].every(Number.isFinite)) throw new Error('Sweep from, to and step must be numbers.');
    if (start < meta.min || start > meta.max || end < meta.min || end > meta.max) throw new Error(`${meta.label} sweep must stay between ${meta.min} and ${meta.max}.`);
    if (end < start) throw new Error('Sweep “To” must be greater than or equal to “From”.');
    if (increment <= 0) throw new Error('Sweep step must be greater than zero.');
    const values = [];
    for (let value = start; value <= end + increment * 1e-8; value += increment) {
      values.push(roundValue(value));
      if (values.length > 60) throw new Error('This one-variable sweep is limited to 60 tested values. Increase the step size.');
    }
    if (!values.length) throw new Error('The selected sweep contains no values.');
    return values;
  }

  function matchingRows(meta) {
    if (!meta) return [];
    return [...exits.querySelectorAll('.exit-plan-row')].filter((row) => {
      const selector = meta.component === 'stop' ? '.exit-stop-family' : '.exit-target-family';
      return row.querySelector(selector)?.value === meta.family;
    });
  }
  function releaseRows() {
    for (const row of exits.querySelectorAll('.exit-plan-row')) {
      row.style.removeProperty('opacity'); row.style.removeProperty('pointer-events'); row.hidden = false;
      delete row.dataset.sweepBound; delete row.dataset.sweepExtra;
    }
  }
  function activateTargetOnFirstPlan(meta) {
    if (meta.component !== 'target') return null;
    const row = exits.querySelector('.exit-plan-row');
    if (!row) return null;
    const targetFamily = row.querySelector('.exit-target-family');
    if (!targetFamily) return null;
    targetFamily.value = meta.family;
    targetFamily.dispatchEvent(new Event('change', {bubbles:true}));
    row.scrollIntoView({block:'nearest', behavior:'smooth'});
    return row;
  }
  function bindRows() {
    releaseRows();
    const meta = META[variable.value];
    if (!meta) { boundNotice.hidden = true; return null; }
    let rows = matchingRows(meta);
    let autoActivated = false;
    if (!rows.length && meta.component === 'target') {
      const activated = activateTargetOnFirstPlan(meta);
      if (activated) { rows = matchingRows(meta); autoActivated = rows.length > 0; }
    }
    if (!rows.length) {
      boundNotice.hidden = false;
      boundNotice.innerHTML = meta.component === 'target'
        ? '<strong>Add an exit plan first.</strong> A profit-target sweep needs one managed exit plan in Section 3 so SCOUT knows which protective stop remains fixed.'
        : `<strong>Needs a matching exit plan.</strong> Add one ${meta.label} plan in Section 3, then select this research variable again.`;
      return null;
    }
    const template = rows[0];
    template.dataset.sweepBound = '1'; template.style.opacity = '.72';
    for (const row of rows.slice(1)) { row.dataset.sweepBound = '1'; row.dataset.sweepExtra = '1'; row.hidden = true; }
    boundNotice.hidden = false;
    const activationText = autoActivated
      ? `<strong>Profit target enabled automatically.</strong> SCOUT attached ${meta.label} to the first exit plan in Section 3 and kept that plan's protective stop fixed. `
      : `<strong>Under test:</strong> ${meta.label}. The highlighted exit plan supplies the fixed partner component. `;
    boundNotice.innerHTML = activationText + `Section 5 controls the swept value. <button id="sweep-use-single" type="button">Use one exact value instead</button>`;
    document.getElementById('sweep-use-single')?.addEventListener('click', () => {
      const extras = [...exits.querySelectorAll('[data-sweep-extra="1"]')]; extras.forEach((row) => row.remove());
      variable.value = ''; lastVariable = ''; refresh(false);
    });
    return template;
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
    if (!meta) { from.disabled = true; to.disabled = true; step.disabled = true; preview.textContent = 'No research variable selected. Your exact exit plans above will be used.'; return; }
    from.disabled = false; to.disabled = false; step.disabled = false;
    try {
      const values = valuesForCurrentSweep();
      const display = values.length <= 14 ? values.join(', ') : `${values.slice(0, 6).join(', ')} … ${values.slice(-3).join(', ')}`;
      preview.innerHTML = `<strong>${values.length} predeclared values:</strong> ${display} ${meta.unit}. The entire range is retained; SCOUT does not select only the historical winner.`;
    } catch (error) { preview.innerHTML = `<strong>Fix sweep:</strong> ${error.message || String(error)}`; }
  }
  function refresh(restoreQuery = false) {
    const meta = META[variable.value];
    if (meta && (restoreQuery || variable.value !== lastVariable)) setDefaults(meta, restoreQuery);
    bindRows(); renderPreview(); lastVariable = variable.value;
  }

  variable.addEventListener('change', () => refresh(false));
  from.addEventListener('input', renderPreview); to.addEventListener('input', renderPreview); step.addEventListener('input', renderPreview);

  function planToken(row, meta, sweptValue) {
    const stopFamily = row.querySelector('.exit-stop-family').value;
    const targetFamily = row.querySelector('.exit-target-family').value;
    const stopValue = meta.component === 'stop' ? sweptValue : Number(row.querySelector('.exit-stop-value').value);
    if (!Number.isFinite(stopValue)) throw new Error('Bound protective stop value is invalid.');
    if (targetFamily === 'none') {
      if (meta.component === 'target') throw new Error('Choose a profit-target type in Section 3 before running this target sweep.');
      return `${stopFamily}:${stopValue}|none:`;
    }
    const targetValue = meta.component === 'target' ? sweptValue : Number(row.querySelector('.exit-target-value').value);
    if (!Number.isFinite(targetValue)) throw new Error('Bound profit target value is invalid.');
    return `${stopFamily}:${stopValue}|${targetFamily}:${targetValue}`;
  }

  form.addEventListener('submit', (event) => {
    if (event.defaultPrevented || !variable.value) return;
    try {
      const meta = META[variable.value];
      const template = matchingRows(meta)[0];
      if (!template) throw new Error(meta.component === 'target' ? 'Add an exit plan in Section 3; SCOUT will attach the selected profit-target sweep to it.' : `Add one matching ${meta.label} exit plan before running the sweep.`);
      form.querySelectorAll('input[name="exit_plan"][data-sweep-gen="1"]').forEach((node) => node.remove());
      for (const value of valuesForCurrentSweep()) {
        const hidden = document.createElement('input'); hidden.type = 'hidden'; hidden.name = 'exit_plan'; hidden.value = planToken(template, meta, value); hidden.dataset.sweepGen = '1'; form.append(hidden);
      }
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
  function parameterFromLabel(label, key) {
    const patterns = {
      fixed: /^Fixed ([0-9.]+)% stop/,
      trailing: /^Trailing ([0-9.]+)% stop/,
      atr: /^ATR ([0-9.]+)x stop/,
      trailing_atr: /^Trailing ATR ([0-9.]+)x stop/,
      target_fixed: /take profit at \+([0-9.]+)%/,
      target_atr: /take profit at \+([0-9.]+)x ATR/,
      target_r: /take profit at \+([0-9.]+)R/,
    };
    const match = patterns[key]?.exec(label); return match ? Number(match[1]) : null;
  }
  function renderSweepResults() {
    const meta = META[variable.value]; if (!meta) return;
    const table = [...document.querySelectorAll('table')].find((node) => node.closest('.card')?.querySelector('h2')?.textContent?.trim() === 'Exit comparison on frozen entry population');
    if (!table) return;
    const headers = [...table.querySelectorAll('thead th')].map((node) => node.textContent.trim());
    const byName = Object.fromEntries(headers.map((name, index) => [name, index]));
    const rows = [...table.querySelectorAll('tbody tr')];
    const holdRow = rows.find((row) => row.cells[0]?.textContent?.trim().startsWith('Hold to maximum period'));
    const holdExpectancy = holdRow ? parsePercent(holdRow.cells[byName.Expectancy]?.textContent) : null;
    const points = rows.map((row) => {
      const value = parameterFromLabel(row.cells[0]?.textContent?.trim() || '', variable.value);
      if (value === null) return null;
      return {value, n:Number(row.cells[byName.N]?.textContent?.trim()), expectancy:parsePercent(row.cells[byName.Expectancy]?.textContent), delta:parsePercent(row.cells[byName['Delta vs hold']]?.textContent), stopOut:parsePercent(row.cells[byName['Stop-out']]?.textContent), targetHit:parsePercent(row.cells[byName['Target-hit']]?.textContent), p05:parsePercent(row.cells[byName.P05]?.textContent)};
    }).filter((item) => item && item.expectancy !== null).sort((a, b) => a.value - b.value);
    if (!points.length) return;
    const width=900,height=300,left=62,right=24,top=26,bottom=52;
    const xMin=points[0].value,xMax=points[points.length-1].value;
    const yValues=points.map((point)=>point.expectancy); if (holdExpectancy!==null) yValues.push(holdExpectancy);
    let yMin=Math.min(...yValues),yMax=Math.max(...yValues); const padding=Math.max(0.5,(yMax-yMin)*0.15); yMin-=padding;yMax+=padding;
    const x=(value)=>left+(xMax===xMin?0.5:(value-xMin)/(xMax-xMin))*(width-left-right);
    const y=(value)=>top+(yMax-value)/(yMax-yMin)*(height-top-bottom);
    const polyline=points.map((point)=>`${x(point.value).toFixed(1)},${y(point.expectancy).toFixed(1)}`).join(' ');
    const circles=points.map((point)=>`<circle cx="${x(point.value).toFixed(1)}" cy="${y(point.expectancy).toFixed(1)}" r="5" fill="#f1c84b"><title>${point.value}${meta.unit}: expectancy ${point.expectancy>=0?'+':''}${point.expectancy.toFixed(2)}%, N=${point.n}</title></circle>`).join('');
    const holdLine=holdExpectancy===null?'':`<line x1="${left}" x2="${width-right}" y1="${y(holdExpectancy).toFixed(1)}" y2="${y(holdExpectancy).toFixed(1)}" stroke="#98a6b8" stroke-dasharray="6 5"/><text x="${width-right}" y="${(y(holdExpectancy)-6).toFixed(1)}" text-anchor="end" fill="#98a6b8" font-size="12">Hold control ${holdExpectancy>=0?'+':''}${holdExpectancy.toFixed(2)}%</text>`;
    const resultCard=document.createElement('div'); resultCard.id='strategy-sweep-results'; resultCard.className='card s12';
    const tableRows=points.map((point)=>`<tr><td>${point.value}${meta.unit}</td><td>${point.n}</td><td>${point.expectancy>=0?'+':''}${point.expectancy.toFixed(2)}%</td><td>${point.delta===null?'—':`${point.delta>=0?'+':''}${point.delta.toFixed(2)}%`}</td><td>${point.stopOut===null?'—':`${point.stopOut.toFixed(1)}%`}</td><td>${point.targetHit===null?'—':`${point.targetHit.toFixed(1)}%`}</td><td>${point.p05===null?'—':`${point.p05.toFixed(2)}%`}</td></tr>`).join('');
    resultCard.innerHTML=`<h2>One-variable sweep — ${meta.label}</h2><div class="section-note"><strong>Read the shape, not just the peak.</strong> The partner stop/target stays fixed while this one value changes. Broad stable regions matter more than isolated historical maxima.</div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Expectancy across ${meta.label} sweep" style="width:100%;min-height:260px;background:#10151d;border:1px solid #293241;border-radius:10px"><line x1="${left}" x2="${left}" y1="${top}" y2="${height-bottom}" stroke="#657184"/><line x1="${left}" x2="${width-right}" y1="${height-bottom}" y2="${height-bottom}" stroke="#657184"/>${holdLine}<polyline points="${polyline}" fill="none" stroke="#f1c84b" stroke-width="3"/>${circles}<text x="${left}" y="${height-18}" fill="#98a6b8" font-size="12">${xMin}${meta.unit}</text><text x="${width-right}" y="${height-18}" text-anchor="end" fill="#98a6b8" font-size="12">${xMax}${meta.unit}</text></svg><div class="scroll"><table><thead><tr><th>${meta.label}</th><th>N</th><th>Expectancy</th><th>Delta vs hold</th><th>Stop-out</th><th>Target-hit</th><th>P05</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
    const grid=document.querySelector('.grid'); if (grid) grid.append(resultCard);
  }

  refresh(Boolean(initialVariable)); renderSweepResults();
})();
"""

__all__ = ["STRATEGY_BUILDER_SWEEP_JS"]
