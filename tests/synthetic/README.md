# Synthetic Tests

Synthetic tests use deterministic artificial market histories with known expected behavior. They are designed to exercise analytical modules without depending on live providers or the local canonical dataset.

The initial laboratory is implemented in `trade_scout.synthetic` and includes clean trends, consolidation breakouts, false breakouts, missing sessions, split discontinuities, volatility shocks, nested bases, gap-downs, stop-outs, and ambiguous daily bars.

Each scenario exposes vendor-independent `ResearchBar` records plus explicit annotations describing the behavior intentionally embedded in the series. Split scenarios also expose both raw and split-adjusted representations and a canonical corporate-action record.
