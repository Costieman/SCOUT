# ruff: noqa: E501
"""Presentation-only plain-English result readout for Strategy Builder."""

STRATEGY_BUILDER_READOUT_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy') return;

  const table = [...document.querySelectorAll('table')].find((node) =>
    node.closest('.card')?.querySelector('h2')?.textContent?.trim() ===
      'Exit comparison on frozen entry population'
  );
  if (!table || document.getElementById('plain-english-readout')) return;

  const headers = [...table.querySelectorAll('thead th')].map((node) => node.textContent.trim());
  const index = Object.fromEntries(headers.map((name, position) => [name, position]));
  const rows = [...table.querySelectorAll('tbody tr')].map((row) => [...row.querySelectorAll('td')]);
  if (!rows.length) return;

  const number = (text) => {
    const parsed = Number(String(text).replaceAll(',', '').replace('%', '').replace('+', '').trim());
    return Number.isFinite(parsed) ? parsed : null;
  };
  const cell = (row, name) => index[name] === undefined ? null : row[index[name]];
  const rowLabel = (row) => row[0]?.textContent?.trim() || '';
  const hold = rows.find((row) => rowLabel(row).startsWith('Hold to maximum holding period')) || rows[0];
  const alternatives = rows.filter((row) => row !== hold);
  const holdExpectancy = number(cell(hold, 'Expectancy')?.textContent);
  const holdPf = number(cell(hold, 'PF')?.textContent);
  const holdP05 = number(cell(hold, 'P05')?.textContent);
  const sample = number(cell(hold, 'N')?.textContent);

  const tones = {
    positive: {word: 'GREEN · Positive', color: '#63d39a', background: '#10241b'},
    caution: {word: 'ORANGE · Caution', color: '#f1c84b', background: '#28220f'},
    negative: {word: 'RED · Negative', color: '#ef7b7b', background: '#291415'},
    neutral: {word: 'GRAY · Information', color: '#aab5c3', background: '#171d27'},
  };

  function signal(label, tone, headline, detail) {
    const style = tones[tone];
    return `<div style="border:1px solid ${style.color};background:${style.background};border-radius:10px;padding:13px;min-height:132px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:${style.color};font-weight:800">${style.word}</div>
      <div style="color:#98a6b8;font-size:11px;text-transform:uppercase;margin-top:8px">${label}</div>
      <strong style="display:block;font-size:17px;margin:5px 0">${headline}</strong>
      <div style="color:#c6cfda">${detail}</div>
    </div>`;
  }

  let payoffTone = 'neutral';
  let payoffHeadline = 'Historical payoff unavailable';
  let payoffDetail = 'There are not enough completed outcomes to summarize the average modeled trade return.';
  if (holdExpectancy !== null) {
    if (holdExpectancy > 0 && (holdPf === null || holdPf > 1)) {
      payoffTone = 'positive'; payoffHeadline = 'Positive in this historical sample';
    } else if (holdExpectancy < 0 && (holdPf === null || holdPf < 1)) {
      payoffTone = 'negative'; payoffHeadline = 'Negative in this historical sample';
    } else {
      payoffTone = 'caution'; payoffHeadline = 'Mixed historical payoff';
    }
    payoffDetail = `Average modeled trade return was ${holdExpectancy >= 0 ? '+' : ''}${holdExpectancy.toFixed(2)}% over the configured maximum holding period. This is not annualized portfolio return or a forecast.`;
  }

  let exitTone = 'neutral';
  let exitHeadline = 'No alternative exit compared';
  let exitDetail = 'Hold-to-maximum-period is the only exit policy in this run.';
  let bestAlternative = null;
  if (alternatives.length) {
    const withDelta = alternatives
      .map((row) => ({row, delta: number(cell(row, 'Delta vs hold')?.textContent)}))
      .filter((item) => item.delta !== null);
    if (withDelta.length) {
      bestAlternative = withDelta.reduce((best, item) => item.delta > best.delta ? item : best);
      if (bestAlternative.delta > 0.25) {
        exitTone = 'positive'; exitHeadline = 'A tested exit improved average return';
      } else if (withDelta.every((item) => item.delta < -0.25)) {
        exitTone = 'negative'; exitHeadline = 'Every tested exit reduced average return';
      } else {
        exitTone = 'caution'; exitHeadline = 'Exit effect is small or mixed';
      }
      exitDetail = `Highest tested difference versus hold was ${bestAlternative.delta >= 0 ? '+' : ''}${bestAlternative.delta.toFixed(2)} percentage points. The ±0.25-point traffic-light boundary is only a display aid, not statistical significance.`;
      const alternativeP05 = number(cell(bestAlternative.row, 'P05')?.textContent);
      if (holdP05 !== null && alternativeP05 !== null) {
        const change = alternativeP05 - holdP05;
        if (Math.abs(change) >= 0.05) exitDetail += ` Its 5th-percentile outcome changed by ${change >= 0 ? '+' : ''}${change.toFixed(2)} points versus hold.`;
      }
    }
  }

  const pageText = document.body.textContent || '';
  const exploratory = pageText.includes('Research state: EXPLORATORY');
  const evidenceTone = exploratory ? 'caution' : 'neutral';
  const evidenceHeadline = exploratory ? 'Exploratory — not validated' : 'Check the registered research state';
  const evidenceDetail = exploratory
    ? 'These results describe this tested historical sample. They do not yet establish long-term or out-of-sample profitability.'
    : 'Confidence should come from the registered validation state, uncertainty and out-of-sample tests—not from return alone.';

  const summaryParts = [];
  if (sample !== null && holdExpectancy !== null) {
    summaryParts.push(`Across ${sample.toLocaleString()} complete historical events, the hold baseline averaged ${holdExpectancy >= 0 ? '+' : ''}${holdExpectancy.toFixed(2)}% per modeled trade after the configured execution costs.`);
  }
  if (bestAlternative) {
    const bestExpectancy = number(cell(bestAlternative.row, 'Expectancy')?.textContent);
    if (bestExpectancy !== null) summaryParts.push(`The highest-expectancy alternative exit averaged ${bestExpectancy >= 0 ? '+' : ''}${bestExpectancy.toFixed(2)}%, ${bestAlternative.delta >= 0 ? '+' : ''}${bestAlternative.delta.toFixed(2)} points versus hold.`);
  }
  summaryParts.push('Overlapping trades, portfolio capital limits and compounding are not represented by these per-trade averages.');

  let nextQuestion = 'Keep the entry definition fixed and vary one parameter at a time; look for a stable region rather than a single historical optimum.';
  if (!alternatives.length) {
    nextQuestion = 'Add one exit family—or use the upcoming one-variable sweep—to learn whether trade management changes the outcome distribution.';
  } else if (bestAlternative?.delta > 0) {
    nextQuestion = 'Test nearby values of that same exit parameter. A broad plateau is more credible than one isolated best value.';
  } else if (bestAlternative && holdP05 !== null) {
    const alternativeP05 = number(cell(bestAlternative.row, 'P05')?.textContent);
    if (alternativeP05 !== null && alternativeP05 > holdP05) {
      nextQuestion = 'The exit appears to trade some return for downside control. Sweep one exit parameter to map that risk/return trade-off instead of picking one value by eye.';
    }
  }

  const card = document.createElement('div');
  card.id = 'plain-english-readout'; card.className = 'card s12';
  card.innerHTML = `<h2>Plain-English research readout</h2>
    <div class="section-note"><strong>How to read this:</strong> the traffic lights summarize already-computed descriptive results. They are not a validation score and do not predict future profitability.</div>
    <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0">
      ${signal('Historical payoff', payoffTone, payoffHeadline, payoffDetail)}
      ${signal('Exit vs hold', exitTone, exitHeadline, exitDetail)}
      ${signal('Evidence status', evidenceTone, evidenceHeadline, evidenceDetail)}
    </div>
    <p style="font-size:15px;line-height:1.6"><strong>In plain English:</strong> ${summaryParts.join(' ')}</p>
    <div class="section-note"><strong>Useful next question:</strong> ${nextQuestion}</div>`;
  table.closest('.card').insertAdjacentElement('beforebegin', card);
})();
"""

__all__ = ["STRATEGY_BUILDER_READOUT_JS"]
