# Pattern & Event Engine foundation

This checkpoint implements the first typed, vendor-independent PatternState and EventRecord contracts described by the Pattern & Event Engine specification.

## Included

- Explicit lifecycle vocabulary: NONE, FORMING, QUALIFIED, TRIGGER_READY, INVALIDATED, CONSUMED.
- Deterministic consolidation pattern identity that persists across one active structural episode.
- Point-in-time support/resistance boundaries computed only from information available at the state timestamp.
- Close-confirmed upside breakout events evaluated against the prior session's stored resistance boundary.
- One event per pattern instance in the event generator.
- Upstream eligibility and quality gates: quarantined/non-eligible bars cannot generate normal events.
- Synthetic tests for flat bases, invalidation, breakout boundary timing, duplicate suppression, future-data leakage, and prefix/batch equivalence.

## Deliberately excluded

This checkpoint does not calculate forward returns, judge profitability, optimize stops, rank candidates, issue alerts, or repair source data. Trend context, ATR/volatility tightness variants, nested-pattern relationships, market-regime context, explicit trading-calendar incremental state storage, and corporate-action restart policy remain later Pattern & Event Engine work.

## Point-in-time rule

A close breakout on session `t` is compared with the resistance boundary stored in the pattern state from session `t-1`. The trigger bar therefore cannot redefine the boundary used to decide whether its own breakout occurred.

## Incremental equivalence

The current detector is deterministic and stateless at the API boundary. The synthetic suite verifies that recomputing each prefix produces the same latest state as the corresponding full-batch result. A future persisted incremental runner may cache state, but it must preserve this equivalence.
