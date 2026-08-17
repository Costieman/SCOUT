"""Presentation-only clarity and execution-profile controls for Strategy Builder.

This companion asset does not change research calculations. It makes execution assumptions explicit,
hides irrelevant numeric controls for boolean trigger conditions, and labels the current research
horizon according to its actual forced-exit semantics.
"""

STRATEGY_BUILDER_CLARITY_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;

  const form = document.getElementById('strategy-form');
  if (!form) return;

  const freshLoad = !window.location.search;
  const byName = (name) => form.querySelector(`[name="${name}"]`);

  function setLabelText(control, text) {
    const label = control?.closest('label');
    if (!label) return;
    const first = label.firstChild;
    if (first && first.nodeType === Node.TEXT_NODE) first.textContent = text;
  }

  const horizon = byName('horizon');
  setLabelText(horizon, 'Maximum holding period (forced exit)');

  const signalLimit = byName('per_session_limit');
  setLabelText(signalLimit, 'Daily signal cap (500 = current app maximum)');

  const rankFeature = byName('rank_feature');
  const rankDirection = byName('rank_direction');
  setLabelText(rankFeature, 'Ranking metric (used only when capped)');
  setLabelText(rankDirection, 'Ranking direction');

  const scopeCard = horizon?.closest('.card');
  if (scopeCard && !scopeCard.querySelector('.horizon-semantics-note')) {
    const note = document.createElement('div');
    note.className = 'section-note horizon-semantics-note';
    note.innerHTML = '<strong>Current exit-duration behavior:</strong> if no stop triggers, SCOUT closes the simulated trade at this maximum holding period. This is a real forced exit, not merely a reporting window. Open-ended "hold until the stop triggers" research needs a separate censored/open-position mode and is not yet represented by this control.';
    scopeCard.append(note);
  }

  let rankingNote = scopeCard?.querySelector('.ranking-clarity-note');
  if (scopeCard && !rankingNote) {
    rankingNote = document.createElement('div');
    rankingNote.className = 'section-note ranking-clarity-note';
    scopeCard.append(rankingNote);
  }

  function syncRankingVisibility() {
    const effectivelyAll = Number(signalLimit?.value || 500) >= 500;
    const rankLabel = rankFeature?.closest('label');
    const directionLabel = rankDirection?.closest('label');
    if (rankLabel) rankLabel.hidden = effectivelyAll;
    if (directionLabel) directionLabel.hidden = effectivelyAll;
    if (rankingNote) {
      rankingNote.textContent = effectivelyAll
        ? 'All qualifying signals are retained up to the current 500-signal application ceiling; ranking is inactive.'
        : 'The daily cap is active. Ranking only decides which already-qualified signals are retained; it is not an entry condition.';
    }
  }
  signalLimit?.addEventListener('input', syncRankingVisibility);
  syncRankingVisibility();

  const executionHeading = [...document.querySelectorAll('.card h2')]
    .find((node) => node.textContent?.trim() === '4. Execution assumptions');
  const executionCard = executionHeading?.closest('.card');
  const entrySlip = byName('entry_slip');
  const exitSlip = byName('exit_slip');
  const stopSlip = byName('stop_slip');
  const commission = byName('commission');

  setLabelText(entrySlip, 'Entry slippage (bps)');
  setLabelText(exitSlip, 'Normal exit slippage (bps)');
  setLabelText(stopSlip, 'Additional stop slippage (bps)');
  setLabelText(commission, 'Commission (bps per side)');

  const profiles = {
    scout_liquid_us: {entry: 5, exit: 5, stop: 10, commission: 0},
    idealized_zero: {entry: 0, exit: 0, stop: 0, commission: 0},
  };

  function setCosts(profile) {
    if (!entrySlip || !exitSlip || !stopSlip || !commission) return;
    entrySlip.value = String(profile.entry);
    exitSlip.value = String(profile.exit);
    stopSlip.value = String(profile.stop);
    commission.value = String(profile.commission);
  }

  if (executionCard && !document.getElementById('execution-profile')) {
    const block = document.createElement('div');
    block.className = 'section-note';
    block.innerHTML = `
      <label style="max-width:520px">Execution profile
        <select id="execution-profile">
          <option value="scout_liquid_us">SCOUT baseline — liquid US equities</option>
          <option value="idealized_zero">Idealized / frictionless</option>
          <option value="custom">Custom</option>
        </select>
      </label>
      <div style="margin-top:8px"><strong>SCOUT baseline:</strong> 5 bps entry slippage, 5 bps normal-exit slippage, an additional 10 bps on stop exits, and 0 bps explicit commission. These are conservative research assumptions, not a universal market standard. Stop slippage is added on top of normal exit slippage, so the baseline models 15 bps of slippage on a stop fill before commissions.</div>
      <div class="subtle" style="margin-top:6px">1 basis point (bp) = 0.01%. Keep every field adjustable for a specific broker, venue, order type, liquidity bucket, or measured execution profile.</div>`;
    executionHeading.insertAdjacentElement('afterend', block);
    const select = block.querySelector('#execution-profile');
    select?.addEventListener('change', () => {
      if (select.value === 'custom') return;
      setCosts(profiles[select.value]);
    });

    const markCustom = () => {
      if (!select) return;
      const values = {
        entry: Number(entrySlip?.value || 0),
        exit: Number(exitSlip?.value || 0),
        stop: Number(stopSlip?.value || 0),
        commission: Number(commission?.value || 0),
      };
      const matching = Object.entries(profiles).find(([, profile]) =>
        profile.entry === values.entry && profile.exit === values.exit &&
        profile.stop === values.stop && profile.commission === values.commission
      );
      select.value = matching?.[0] || 'custom';
    };
    for (const control of [entrySlip, exitSlip, stopSlip, commission]) {
      control?.addEventListener('input', markCustom);
    }
    if (freshLoad) setCosts(profiles.scout_liquid_us);
    markCustom();
  }

  const binaryMetrics = new Set([
    'ma_above', 'ma_below', 'ma_cross_up', 'ma_cross_down',
    'bb_upper_reached', 'bb_lower_reached', 'bb_upper_cross_up',
    'bb_lower_cross_down', 'bb_middle_cross_up', 'bb_middle_cross_down',
    'macd_cross_up', 'macd_cross_down', 'prior_high_breakout',
  ]);

  const conditionDescriptions = {
    ma_above: 'True when the selected price source is above the moving average. No 0/1 value needs to be entered.',
    ma_below: 'True when the selected price source is below the moving average. No 0/1 value needs to be entered.',
    ma_cross_up: 'True only on a trading day when price crosses from at/below the moving average to above it.',
    ma_cross_down: 'True only on a trading day when price crosses from at/above the moving average to below it.',
  };

  function renamePeriod(row) {
    const period = row.querySelector('.param-period');
    if (!period) return;
    const family = row.querySelector('.rule-indicator')?.value;
    const labels = {
      moving_average: 'Moving-average length (trading days)',
      bollinger_bands: 'Bollinger period (trading days)',
      price_roc: 'ROC period (trading days)',
      rsi: 'RSI period (trading days)',
      atr: 'ATR period (trading days)',
      relative_volume: 'RVOL average period (trading days)',
      average_dollar_volume: 'Average period (trading days)',
      historical_volatility: 'Volatility period (trading days)',
      prior_high: 'Prior-high lookback (trading days)',
    };
    setLabelText(period, labels[family] || 'Indicator period (trading days)');
  }

  function syncRuleClarity(row) {
    if (!(row instanceof HTMLElement)) return;
    renamePeriod(row);
    const metric = row.querySelector('.rule-metric')?.value;
    const comparisonLabel = row.querySelector('.rule-operator')?.closest('label');
    const thresholdLabel = row.querySelector('.threshold-label');
    const sliderLabel = row.querySelector('.slider-wrap');
    const unit = row.querySelector('.threshold-unit');
    const semantic = binaryMetrics.has(metric);
    if (comparisonLabel) comparisonLabel.hidden = semantic;
    if (thresholdLabel && semantic) thresholdLabel.hidden = true;
    if (sliderLabel && semantic) sliderLabel.hidden = true;
    if (unit && semantic && conditionDescriptions[metric]) {
      unit.textContent = conditionDescriptions[metric];
    }
  }

  function wireRule(row) {
    if (!(row instanceof HTMLElement) || row.dataset.clarityWired === '1') return;
    row.dataset.clarityWired = '1';
    row.querySelector('.rule-indicator')?.addEventListener('change', () => queueMicrotask(() => syncRuleClarity(row)));
    row.querySelector('.rule-metric')?.addEventListener('change', () => queueMicrotask(() => syncRuleClarity(row)));
    syncRuleClarity(row);
  }

  const ruleContainer = document.getElementById('rule-rows');
  ruleContainer?.querySelectorAll('.rule-row').forEach(wireRule);
  if (ruleContainer) {
    new MutationObserver(() => ruleContainer.querySelectorAll('.rule-row').forEach(wireRule))
      .observe(ruleContainer, {childList: true, subtree: true});
  }
})();
"""

__all__ = ["STRATEGY_BUILDER_CLARITY_JS"]
