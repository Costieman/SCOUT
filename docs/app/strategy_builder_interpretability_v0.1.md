# Strategy Builder Interpretability Layer v0.1

## Purpose

Make the Research Lab understandable without removing technical depth or moving analytical logic into the UI.
The analytical result remains the existing versioned Strategy Builder output; this layer only explains and
organizes those outputs for the operator.

## First-slice behavior

- Add a plain-English result readout above the technical exit-comparison table.
- Use traffic-light presentation only as a descriptive aid, always paired with text labels.
- Separate three questions instead of collapsing evidence into one opaque score:
  - **Historical payoff:** was average modeled return positive or negative in this sample?
  - **Exit vs hold:** did any tested exit improve average return versus the same-event hold control?
  - **Evidence status:** is the result exploratory, validated, rejected, or another registered lifecycle state?
- Explicitly state that per-trade expectancy is not annualized portfolio return and does not establish future
  profitability.
- Keep the full technical table visible beneath the simplified readout.

## Contextual help

The Strategy Builder provides plain-English definitions for research-scope controls, execution assumptions and
technical result metrics including expectancy, profit factor, payoff ratio, P05, MAE, MFE, drawdown and gap-through
frequency. A help control is available where practical; right-clicking supported labels, selected indicators and
conditions also opens the explanation.

Indicator help currently covers Moving Average, Price ROC, RSI, MACD, Bollinger Bands, ATR, Relative Volume,
Average Dollar Volume, Historical Volatility and Price vs Prior High.

## Scientific boundary

The traffic lights are not significance tests, validation gates, forecasts, rankings or strategy-promotion scores.
The exit-vs-hold display uses a visible ±0.25 percentage-point threshold only to avoid visually celebrating tiny
sample differences; the interface explicitly labels this as a display convention rather than statistical significance.
Exploratory results remain visibly exploratory.

This follows the dashboard specification's requirement that interpretability not turn weak evidence into a polished
claim, and the project principle that stability and validation outrank isolated optima.

## Next UI research slice

The next planned Strategy Builder addition is a **one-variable parameter sweep**:

1. Choose one existing numeric analytical parameter as the variable under test.
2. Define `from`, `to`, and `step` (or an explicit value set).
3. Lock/mark the corresponding normal control while the sweep is active.
4. Keep every other resolved setting fixed.
5. Execute the complete predeclared range and retain every tested value.
6. Visualize the result as a parameter curve/surface with sample size, rather than selecting only the best cell.
7. Changing the bound normal control clears or explicitly replaces the active sweep.

Only one parameter is swept in the first implementation to keep the search space interpretable and to avoid an
accidental combinatorial optimizer.

## Deferred ideas

The proposed daily-candle volume-by-price approximation remains a research-hypothesis/backlog item. It is not part
of this interface/interpretability milestone.
