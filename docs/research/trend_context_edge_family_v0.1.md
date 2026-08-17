# Canonical-Only T0–T5 Trend Context Edge Family v0.1

## Purpose

This operator answers the next research question after the holding-horizon family failed to establish incremental consolidation-breakout edge: which registered trend component, if any, adds continuation over its simpler parent rule?

It deliberately stays on the selected immutable reviewed-canonical dataset and makes no provider calls. T6 is not guessed or approximated when the explicit market benchmark is absent.

## Fixed research choices

The family keeps the following fixed within one run:

- reviewed canonical fixed cohort;
- one immutable canonical dataset version;
- analysis window;
- next-session-open entry semantics;
- one daily-session outcome horizon;
- anti-clustering sampling stride;
- 200-session and 50-session SMA definitions;
- 200-SMA slope lookback;
- trailing-return interval.

Only the registered trend context changes.

## Contexts and predeclared parent comparisons

- T0: no trend condition; unconditional reference.
- T1: close above 200-session SMA. Parent: T0.
- T2: T1 plus rising 200-session SMA. Parent: T1.
- T3: close above both 50- and 200-session SMAs. Parent: T1.
- T4: T3 plus 50-session SMA above 200-session SMA. Parent: T3.
- T5: T2 plus positive trailing return. Parent: T2.
- T6: not run by this canonical-only family because it requires an explicit broad-market benchmark series.

The parent map is fixed before evaluation so the analysis measures incremental rule components rather than retrospectively choosing whichever comparator looks easiest to beat.

## Evidence

For every T0–T5 context the report shows sample size, raw mean and median forward return, win rate, profit factor, median MFE/MAE and a calendar-month cluster-bootstrap 95% interval for the raw mean.

For T1–T5 it additionally computes the child-minus-parent difference in mean return separately within each common calendar month. Those monthly differences are summarized as a paired-month increment, bootstrapped for a 95% interval, and tested with a deterministic sign-flip randomization test.

Benjamini-Hochberg correction is applied across the five predeclared T1–T5 parent-increment hypotheses.

## Preliminary diagnostic gate

A child context clears the exploratory gate only when all of the following hold:

1. its clustered raw-mean 95% interval is fully above zero;
2. its paired-month increment over its parent is positive;
3. the paired-month increment 95% interval is fully above zero; and
4. the parent-increment randomization p-value remains below alpha after Benjamini-Hochberg correction across T1–T5.

Passing this gate does not validate a strategy. The research state remains `EXPLORATORY`; T6, broader research-family correction, historical point-in-time membership, portfolio simulation and genuine out-of-sample validation remain incomplete.

## Operator

```powershell
uv run python scripts/run_trend_context_edge_family.py `
  --root "C:\Users\Lucille Lacoste\trade-scout-private" `
  --lookback-years 2 `
  --horizon 20 `
  --sampling-stride 5 `
  --sma-slope-lookback 20 `
  --trailing-return-intervals 60 `
  --open-browser
```

The command writes checksummed JSON and printable HTML under `evidence/trend-context-edge-family/` in the private workspace and explicitly reports `provider_calls_made: false`.
