"""Fresh-load behavior for the interactive Strategy Builder.

The main Strategy Builder asset preserves submitted and example configurations. This small
presentation-only companion runs only when the operator opens ``/research/strategy`` without a
query string, removing opinionated example conditions/stops from the first impression.
"""

STRATEGY_BUILDER_CLEAN_DEFAULTS_JS = r"""
(() => {
  'use strict';
  if (window.location.pathname !== '/research/strategy' || window.location.search) return;

  const rules = document.getElementById('rule-rows');
  const stops = document.getElementById('stop-rows');
  const signalLimit = document.querySelector('input[name="per_session_limit"]');

  function addEmptyState(container, selector, text) {
    if (!container) return;
    container.replaceChildren();
    const note = document.createElement('div');
    note.textContent = text;
    note.style.margin = '8px 0';
    note.style.padding = '12px';
    note.style.border = '1px dashed #3a4657';
    note.style.borderRadius = '9px';
    note.style.color = '#98a6b8';
    note.style.background = '#10151d';
    container.append(note);

    const sync = () => {
      note.hidden = container.querySelector(selector) !== null;
    };
    new MutationObserver(sync).observe(container, {childList: true});
    sync();
  }

  addEmptyState(
    rules,
    '.rule-row',
    'No entry conditions selected. Use + Add condition to build the hypothesis.'
  );
  addEmptyState(
    stops,
    '.stop-row',
    'No additional exit candidates selected. Hold-to-horizon remains the control.'
  );

  if (signalLimit) {
    signalLimit.value = '500';
    signalLimit.title = '500 is the current application maximum and avoids truncating the present reviewed cohort.';
  }
})();
"""

__all__ = ["STRATEGY_BUILDER_CLEAN_DEFAULTS_JS"]
