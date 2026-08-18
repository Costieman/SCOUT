# Composite exit plans

Trade Scout now treats post-entry management as a **plan** rather than assuming that every exit
candidate is a mutually exclusive philosophy.

A managed exit plan contains:

1. one protective stop;
2. an optional profit target; and
3. the configured maximum holding period as the final research backstop.

The simulated position exits on the first configured stop or target trigger. If neither occurs, the
maximum holding period ends the research path. The pure hold-to-maximum result remains beside the
managed plans as a scientific control so the system can measure whether the exit policy improved or
damaged the same frozen entry population. It is not presented as a recommendation to trade without
a protective stop.

## Supported v1 components

Protective stops reuse the existing generic risk engine:

- fixed percentage stop;
- trailing percentage stop;
- ATR-multiple stop;
- trailing ATR-multiple stop.

Profit targets are now explicit policy components:

- fixed percentage gain;
- ATR multiple above entry;
- R multiple, where `R` is the initial entry-to-protective-stop risk.

The UI materializes each user-declared combination as one policy. It does **not** silently build a
Cartesian product of every stop and target value.

## Daily-bar ordering

Daily OHLC data cannot reveal intraday order when a bar trades through both the active stop and the
profit target. Such cases are recorded as ambiguous. The Strategy Builder exposes an explicit
same-bar assumption:

- `STOP_FIRST` is the conservative default;
- `TARGET_FIRST` is an optimistic sensitivity case.

A threshold already crossed at the session open is different: the open is known before the later
intraday high/low range, so a gap above a target or below a stop is resolved at the open rather than
being treated as an unknowable same-bar sequence.

Trailing stops retain the existing conservative update rule: session *t* can tighten the stop only
for session *t+1*. The engine never uses today's eventual high to claim a stop was active before
today's earlier low.

## One-variable research sweeps

Section 5 can bind one stop distance or one target value as the research variable. The partner
stop/target component remains fixed, and the full declared range is retained. This is intended to
show broad response regions rather than celebrate a single historical maximum.

## Explicitly deferred: partial scale-outs

A rule such as “sell 25% at +10%, then trail the remaining 75%” is not equivalent to one terminal
exit. It requires position-leg accounting, remaining quantity, weighted realized return, target-leg
ordering, and cost allocation. The current managed-exit contract therefore closes the full simulated
position at one terminal stop or target. Partial exits should enter a separate, tested position-leg
extension rather than being approximated inside this first implementation.

## Research boundary

All managed-exit parameters are stored in the immutable resolved experiment configuration. Exit
policies are applied only after the entry event population is frozen, and the same complete event IDs
must be used across policy comparisons. Results remain `EXPLORATORY` until the normal multiplicity,
robustness, and out-of-sample requirements are satisfied.
