# Outcome Path Measurement

## Purpose

The canonical outcome-path layer measures what happened after an already-defined `EventRecord`.
It does not decide whether an event existed and it does not apply stop-loss, profit-target,
position-sizing, or trade-management rules. Those policies belong to the downstream risk research
layer and must be compared against the same unmanaged outcome paths.

## Entry and horizon semantics

Close-confirmed events use next-observed-session open as the entry price. A requested horizon is a
count of observed research sessions beginning with that entry session. Complete horizons report the
close-to-entry forward return. Incomplete horizons are retained explicitly rather than silently
removed.

`OutcomePathStatus` distinguishes:

- `COMPLETE`;
- `NO_ENTRY_BAR` when no next session exists;
- `ENTRY_UNUSABLE` when the next session is not eligible and quality `PASS`;
- `TRUNCATED_END_OF_DATA`; and
- `TRUNCATED_UNUSABLE_BAR`.

Partial usable paths retain MAE, MFE, drawdown, gap, timing, and mark-to-last-observed-close metrics,
but their requested-horizon `forward_return` remains null.

## Path measurements

For each event/horizon pair the layer records:

- forward return and partial return;
- maximum favorable excursion (MFE) and maximum adverse excursion (MAE);
- session offsets and dates of MFE and MAE;
- observable ordering of those extremes across daily bars;
- entry gap and largest positive/negative observed overnight gaps; and
- maximum-drawdown bounds.

The time-to-extreme convention is zero-based from the entry session, so an extreme occurring on the
entry day has an offset of `0`.

## Daily-bar ambiguity

Daily OHLC data do not reveal whether the session high occurred before or after the session low.
The outcome layer therefore does not invent intraday ordering. When the horizon-wide MFE and MAE
occur on the same daily bar, `ExtremeOrder.SAME_BAR_AMBIGUOUS` is emitted.

Maximum drawdown is reported as an interval. The lower bound is the more severe value possible when
a same-session new high may precede that session's low. The upper bound uses only peaks that are
known to have existed before the current session. If those bounds differ,
`intraday_drawdown_ambiguous` is true.

This ambiguity is descriptive only. It does not infer whether a hypothetical stop or target would
have executed first; that question belongs to the risk-policy comparison harness.

## Provenance boundary

Outcome measurement fails closed when an event's signal index, signal date, instrument, or dataset
version does not match the supplied research bars. A measurement run also rejects mixed instruments,
dataset versions, or price representations.

## Synthetic verification

The Synthetic Market Laboratory is used to verify the full `EventRecord -> OutcomePath` boundary.
The integration suite covers a generated consolidation breakout, a stop-breach-and-recovery path,
an overnight gap-down, explicit horizon truncation, and a daily bar whose favorable and adverse
extremes have unknowable intraday order.
