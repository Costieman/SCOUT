# Strategy Builder one-variable exit-policy sweep v0.1

## Purpose

Expose the first interactive parameter-sweep workflow without turning the Strategy Builder into an unconstrained
optimizer. The operator selects one exit-policy parameter, declares the full range before execution, and inspects
the complete response curve.

## Supported variables

The first implementation deliberately supports only exit-policy dimensions that preserve the same frozen entry
event population:

- Fixed stop distance (%)
- Trailing stop distance (%)
- ATR stop multiple
- Trailing ATR multiple

The existing generic exit-policy engine already accepts multiple values per family. This UI therefore reuses that
shared engine rather than creating a second sweep/backtest implementation.

## Interaction model

1. Build the entry definition and any fixed comparison exits normally.
2. In **Research variable — one-variable sweep**, select one exit parameter.
3. Set `From`, `To`, and `Step`.
4. SCOUT materializes the complete value list before submission and limits the first UI implementation to 60 values.
5. Matching single-value rows in the normal exit section are hidden and marked as controlled by Section 5.
6. Other exit families remain fixed.
7. The submitted request contains the complete resolved policy grid, so analytical values are not hidden in UI state.
8. Results retain every tested value.

## Result visualization

The result page adds an expectancy curve for the selected variable together with the hold baseline. A companion
table retains parameter value, sample size, expectancy, delta versus hold, stop-out rate and P05 tail outcome.
The chart explicitly instructs the operator to inspect the shape/plateau rather than select a single peak.

The highest observed expectancy is displayed only as a descriptive location to inspect. It is not called a validated
optimum or recommendation.

## Why entry-indicator sweeps are separate

Changing an entry indicator period, threshold, Bollinger deviation, or similar entry condition can change which
historical events exist. That is scientifically different from applying several exit policies to one fixed event set.
The repository already contains experiment-grid expansion machinery in `trade_scout.experiments.sweeps`; a later
entry-parameter sweep should use the experiment/child-run governance path rather than pretending it is the same as
an exit-policy comparison.

## Research boundary

This surface remains exploratory. A sweep maps a parameter response surface; it does not validate the best cell.
Any candidate region still requires registered multiplicity/robustness and out-of-sample procedures before promotion.
