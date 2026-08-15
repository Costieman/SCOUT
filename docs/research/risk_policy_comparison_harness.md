# Risk Policy Comparison Harness

## Purpose

This harness implements the controlled risk-comparison boundary after outcome-path measurement. Entry events remain frozen. Every stop policy is applied to the same eligible event IDs, under the same next-session-open entry convention and the same research horizon.

The harness is exploratory infrastructure. It does not select, validate, or promote a stop policy.

## Architecture boundary

Event-level stop placement, stop triggering, fill assumptions, cost application, and per-event risk results belong to `trade_scout.risk`. Cross-policy aggregation and comparison belong to `trade_scout.statistics`.

Accordingly, `run_risk_policy_comparison()` and the baseline comparison grid are exposed from `trade_scout.statistics`, while the risk module remains independently usable for one-event/one-policy evaluation. This preserves the accepted downstream dependency direction: statistics may consume risk outputs; risk does not import statistical interpretation.

## Policy families

The comparison harness supports:

- no-stop horizon baseline;
- fixed-percentage stops;
- pre-entry ATR stops;
- structural stops using pattern-neutral support/resistance context; and
- an explicit structural/ATR hybrid interface.

The baseline hybrid fixture uses the wider stop for a long position: the lower of consolidation support and `entry - 2 x pre-entry ATR`. This formula exists to exercise the hybrid interface and is not a scientifically preferred stop rule. Any candidate hybrid formula still requires separate empirical validation.

## Frozen event population

Policy summaries are rejected unless every policy contains the exact same event IDs as the no-stop baseline. Equal sample counts are not sufficient. The comparison persists a SHA-256 fingerprint of the common event-ID population.

Events lacking mathematically required ATR history are excluded before the grid is evaluated. Missing structural context for a structural or hybrid policy is treated as an error rather than silently guessed.

Canonical Pattern/Event output is connected to structural risk through `StructuralStopContext`, which is derived from the generic `PatternState` contract. The Risk layer therefore does not import a consolidation detector to recover structural geometry.

## Stop trigger and fill semantics

For long positions:

1. if a session opens at or below the active stop, the opening price is the market exit before configured costs;
2. otherwise, if the daily low touches the stop, the nominal stop is the market exit before configured costs;
3. if no stop occurs, the position exits at the selected research-horizon close.

Gap-through-stop loss is measured explicitly. A stop is never assumed to fill at an unavailable pre-gap price.

## Same-bar ambiguity

The harness does not invent intraday high/low ordering. Premature-stop success definitions are frozen before evaluation. When a stopped event uses a post-stop MFE threshold as the success criterion and the stop plus success threshold are both inside the stop-day OHLC range, the result is `SAME_BAR_AMBIGUOUS`.

Policy summaries therefore report lower and upper bounds for premature-stop rate:

- lower bound: definitely premature stops divided by stopped events;
- upper bound: definitely premature plus same-bar ambiguous cases divided by stopped events.

This does not yet implement target exits or trailing stops. It only prevents same-bar future knowledge from contaminating the premature-stop diagnostic.

## Cost hooks

`CostModel` separates:

- entry slippage;
- ordinary exit slippage;
- additional stop-exit slippage; and
- commission per side.

Event-level results retain gross return, net return, and return drag attributable to the configured cost hooks. Zero-cost runs remain gross exploratory evidence only.

## Comparison outputs

For each policy the descriptive layer retains expectancy, change versus no stop, win probability, winner/loser distributions, profit factor, R-multiples, stop-out rate, premature-stop bounds, gap-through frequency, gap loss, tail return, holding period, MAE before exit, full-horizon MFE, initial risk, and mean cost drag.

These outputs are descriptive research evidence. Policy selection still belongs to the governed experiment and validation workflow.
