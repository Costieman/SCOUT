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

This checkpoint does not calculate forward returns, judge profitability, optimize stops, rank candidates, issue alerts, or repair source data. ATR/volatility tightness variants, nested-pattern relationships, market-regime context, explicit trading-calendar incremental state storage, and corporate-action restart policy remain later Pattern & Event Engine work.

## Point-in-time rule

A close breakout on session `t` is compared with the resistance boundary stored in the pattern state from session `t-1`. The trigger bar therefore cannot redefine the boundary used to decide whether its own breakout occurred. Trend qualification is evaluated on `t`, and optional relative-volume qualification compares `t` volume with a trailing baseline that excludes `t`.

## Event suppression and cooldown semantics

The typed engine uses **one event per pattern instance** as its canonical duplicate-suppression rule. It does not impose a global fixed-session cooldown after an event.

This intentionally differs from the exploratory `consolidation_breakout.py` detector, whose `cooldown_sessions` option can suppress any later candidate occurring within a fixed number of sessions, including a candidate associated with a genuinely new pattern episode. In the typed architecture, invalidation ends one structural episode; a subsequently qualified consolidation receives a new `pattern_instance_id` and may therefore generate its own event even if it occurs only a few sessions later.

If a research experiment still wants a minimum spacing between otherwise valid events, that spacing belongs in a downstream event-selection or portfolio-construction layer. It must not alter canonical pattern identity or erase a valid event from the Pattern & Event Engine.

Because this is an intentional semantic improvement rather than byte-for-byte compatibility, research migrations must version and disclose the difference when comparing historical outputs from the exploratory detector with typed-engine outputs.

## Incremental equivalence

The current detector is deterministic and stateless at the API boundary. The synthetic suite verifies that recomputing each prefix produces the same latest state as the corresponding full-batch result. A future persisted incremental runner may cache state, but it must preserve this equivalence.
