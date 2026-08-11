# Baseline Risk & Stop Research v0.1

## Purpose

This slice implements the first simple stop-policy comparison for the consolidation-breakout research program. It follows the governing Outcome, Risk & Stop-Loss rule: **measure the post-event path first; test risk policies second**. Stop policies never redefine whether the breakout event existed.

## Fixed event and entry semantics

- Event family: close-confirmed consolidation breakout from the existing exploratory detector.
- Entry: next-session open.
- Research horizon: selected before the stop comparison (2, 3, 5, 10, 20, 40, or 60 sessions in the current UI).
- Complete-horizon events only are included in the stop-policy comparison.
- The same complete event population is used for every policy.
- Premature stop v0.1: a stopped event whose no-stop net return is positive at the selected research horizon.

## Policy grid

- No-stop baseline held to the selected horizon.
- Fixed percentage: 2%, 3%, 4%, 5%, 7%, 10%.
- ATR: 1.0x, 1.5x, 2.0x, 2.5x, 3.0x.
- Structural: consolidation low.
- Structural: breakout boundary.
- Structural: breakout boundary minus 0.5 ATR.

ATR is registered in the Feature Engine as `atr_14` v0.1: the simple mean of 14 split-adjusted true ranges ending on the signal date. The calculation therefore uses information known by the close-confirmed signal before next-session-open entry.

## Daily-bar stop fills

The initial policy family contains no profit target, so daily stop/target ordering ambiguity is not introduced. For a long position:

1. If a later session opens at or below the active stop, the market opening price is used before configured exit slippage. This is recorded as gap-through-stop behavior.
2. Otherwise, if the session low reaches the stop, the nominal stop level is used before exit slippage.
3. If no stop is reached, the position exits at the selected research-horizon close before exit slippage.
4. Structural policies whose stop is already at or above the entry opening price are retained and flagged as `ENTRY_AT_OR_BELOW_INITIAL_STOP` rather than silently removed.

## Cost model

The UI exposes explicit basis-point cost per side. The default is zero because the governing specification does not prescribe a universal cost assumption. Zero-cost output is labelled gross exploratory evidence and cannot support a tradability or production claim.

## Reported metrics

The current surface reports sample size, initial risk, stop-out rate, expectancy, expectancy change versus no stop, win probability, profit factor, average R, premature-stop rate, gap-through frequency, 5th-percentile tail return, average holding period, and median MAE before exit. Event-level outputs also retain full-horizon MFE and post-stop MFE for research diagnostics.

## Deliberate exclusions

This slice does not implement trailing stops, targets, realized-volatility stops, VIX conditioning, setup-conditioned empirical stops, transaction-cost calibration, portfolio sizing, validation/promotion, scanner usage, alerts, or brokerage execution. Adaptive stop estimation remains later work and must be time-ordered/walk-forward.
