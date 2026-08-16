# First Research Program — Executable A–J Templates

## Purpose

This layer turns the accepted Consolidation Breakouts Version 0.1 research sequence into versioned, machine-readable experiment templates. It does **not** run the historical research and it does not invent thresholds that the governing research specification deliberately leaves to exploratory resolution.

The implementation preserves the controlled sequence:

- A — trend-only baseline;
- B — consolidation duration;
- C — consolidation tightness;
- D — breakout boundary and confirmation;
- E — volume confirmation;
- F — market-regime conditioning;
- G — stock volatility and trading age;
- H — simple stop-policy comparison;
- I — combined frozen candidate validation; and
- J — walk-forward and final holdout validation.

Experiments A–H are exploratory templates. Experiments I–J are confirmatory templates and therefore materialize no multi-value parameter search once their frozen inputs have been resolved.

## Source-defined grids

The executable templates preserve the parameter families that are explicitly specified in Version 0.1:

- trend contexts T0–T6;
- consolidation durations 10, 15, 20, 25, 30, 40, 50, and 60 sessions;
- forward horizons 5, 10, 20, 40, 60, 120, and 252 sessions;
- fixed stops 2%, 3%, 4%, 5%, 7%, and 10%; and
- ATR stops 1.0x, 1.5x, 2.0x, 2.5x, and 3.0x, plus structural and exploratory hybrid families.

The planner materializes these declared search dimensions before execution so the complete search space is auditable.

## Deliberately unresolved inputs

Several Version 0.1 sections describe broad candidate families without freezing exact thresholds. The template layer keeps these as explicit resolution gates rather than choosing values silently. Examples include:

- the fixed tightness definition used by Experiment B;
- complete method-specific tightness variants for Experiment C;
- percentage and ATR confirmation margins for breakout variants in Experiment D;
- relative-volume and percentile thresholds for Experiment E;
- regime bucket definitions for Experiment F;
- stock-volatility and trading-age buckets for Experiment G; and
- the final frozen candidate, comparator, outcome, validation windows, walk-forward plan, holdout, and promotion criteria for Experiments I–J.

A dry run therefore answers two questions separately: **what the study requires** and **whether those requirements are currently resolved**.

## Preflight behavior

`dry_run_first_program_experiment()` checks:

1. prior A–J dependencies;
2. required data/feature/analytical capabilities;
3. experiment-specific unresolved research inputs;
4. dynamic parameter grids supplied by prior evidence; and
5. the final-holdout protection rule for Experiment J.

If any requirement is missing, the dry run returns explicit blockers and no executable `ExperimentDefinition`. If all requirements are satisfied, it produces the immutable definition and an `ExperimentBatchPlan` using the existing governed experiment planner.

## Scientific boundary

This machinery is orchestration, not evidence. A ready template means only that the experiment is sufficiently specified to run. It does not mean that the underlying hypothesis is supported, that a candidate is validated, or that a strategy is production eligible.

The final holdout is treated specially: if it has already been inspected, the J template refuses to represent it as an untouched final holdout. This prevents repeated inspection from being disguised as independent confirmation.
