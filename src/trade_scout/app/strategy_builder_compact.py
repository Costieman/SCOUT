# ruff: noqa: E501
"""Presentation-only compact rule summaries for Strategy Builder."""

STRATEGY_BUILDER_COMPACT_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;

  const container = document.getElementById('rule-rows');
  if (!container) return;

  const style = document.createElement('style');
  style.textContent = `
    .rule-summary { grid-column:1/-1; display:flex; gap:10px; align-items:center; justify-content:space-between; padding:9px 10px; border:1px solid #334052; border-radius:8px; background:#10151d; }
    .rule-summary-main { display:flex; gap:8px; align-items:center; flex-wrap:wrap; min-width:0; }
    .rule-summary-title { font-weight:760; color:#edf1f7; }
    .rule-summary-detail { color:#98a6b8; font-size:12px; }
    .rule-summary-actions { display:flex; gap:6px; flex:0 0 auto; }
    .rule-summary-actions button { padding:6px 9px; font-size:12px; }
    .rule-row.rule-collapsed > :not(.rule-summary) { display:none !important; }
    .rule-row.rule-collapsed { display:block; padding:8px; }
    @media print {
      .rule-row.rule-collapsed > :not(.rule-summary) { display:none !important; }
      .rule-summary-actions { display:none !important; }
    }
  `;
  document.head.append(style);

  const text = (node) => node?.options?.[node.selectedIndex]?.textContent?.trim() || '';
  const value = (row, selector) => row.querySelector(selector)?.value;

  function parameterText(row) {
    const family = value(row, '.rule-indicator');
    const parts = [];
    const period = value(row, '.param-period');
    const source = value(row, '.param-source');
    if (family === 'moving_average') {
      const type = value(row, '.param-ma-type')?.toUpperCase() || 'MA';
      if (period) parts.push(`${type} ${period}`);
    } else if (family === 'bollinger_bands') {
      const deviations = value(row, '.param-deviations');
      if (period) parts.push(`${period} days`);
      if (deviations) parts.push(`${deviations} SD`);
    } else if (family === 'macd') {
      const fast = value(row, '.param-fast');
      const slow = value(row, '.param-slow');
      const signal = value(row, '.param-signal');
      if (fast && slow && signal) parts.push(`${fast}/${slow}/${signal}`);
    } else if (period) {
      parts.push(`${period} days`);
    }
    if (source && source !== 'close') parts.push(source[0].toUpperCase() + source.slice(1));
    return parts.join(' · ');
  }

  function thresholdText(row) {
    const metric = value(row, '.rule-metric');
    const binary = new Set([
      'ma_above', 'ma_below', 'ma_cross_up', 'ma_cross_down',
      'bb_upper_reached', 'bb_lower_reached', 'bb_upper_cross_up',
      'bb_lower_cross_down', 'bb_middle_cross_up', 'bb_middle_cross_down',
      'macd_cross_up', 'macd_cross_down', 'prior_high_breakout',
    ]);
    if (binary.has(metric)) return '';
    const operator = text(row.querySelector('.rule-operator'));
    const threshold = value(row, '.rule-value');
    const unit = row.querySelector('.threshold-unit')?.textContent?.trim() || '';
    if (threshold === undefined || threshold === '') return '';
    return `${operator} ${threshold}${unit.startsWith('%') ? '%' : ''}`;
  }

  function updateSummary(row) {
    const summary = row.querySelector('.rule-summary');
    if (!summary) return;
    const join = value(row, '.rule-join') === 'or' ? 'OR' : 'AND';
    const indicator = text(row.querySelector('.rule-indicator')) || 'Indicator';
    const condition = text(row.querySelector('.rule-metric')) || 'Condition';
    const parameters = parameterText(row);
    const threshold = thresholdText(row);
    const details = [condition, parameters, threshold].filter(Boolean).join(' · ');
    summary.querySelector('.rule-summary-title').textContent = `${join} · ${indicator}`;
    summary.querySelector('.rule-summary-detail').textContent = details;
  }

  function setCollapsed(row, collapsed) {
    row.classList.toggle('rule-collapsed', collapsed);
    const edit = row.querySelector('.rule-summary-edit');
    if (edit) edit.textContent = collapsed ? 'Edit' : 'Done';
    updateSummary(row);
  }

  function wireRow(row, collapseInitially = false) {
    if (!(row instanceof HTMLElement) || row.dataset.compactWired === '1') return;
    row.dataset.compactWired = '1';
    const summary = document.createElement('div');
    summary.className = 'rule-summary';
    summary.innerHTML = `
      <div class="rule-summary-main">
        <span class="rule-summary-title"></span>
        <span class="rule-summary-detail"></span>
      </div>
      <div class="rule-summary-actions"><button type="button" class="rule-summary-edit">Edit</button></div>`;
    row.prepend(summary);
    summary.querySelector('.rule-summary-edit')?.addEventListener('click', () => {
      setCollapsed(row, !row.classList.contains('rule-collapsed'));
    });
    row.addEventListener('input', () => updateSummary(row));
    row.addEventListener('change', () => queueMicrotask(() => updateSummary(row)));
    setCollapsed(row, collapseInitially);
  }

  const initialRows = [...container.querySelectorAll('.rule-row')];
  const collapseInitial = Boolean(window.location.search);
  initialRows.forEach((row) => wireRow(row, collapseInitial));

  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof HTMLElement)) continue;
        if (node.matches('.rule-row')) wireRow(node, false);
        node.querySelectorAll?.('.rule-row').forEach((row) => wireRow(row, false));
      }
    }
  }).observe(container, {childList: true, subtree: true});
})();
"""

__all__ = ["STRATEGY_BUILDER_COMPACT_JS"]
