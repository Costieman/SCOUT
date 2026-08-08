# ADR-0006: Split-adjustment factor semantics

**Status:** Accepted  
**Date:** 2026-08-08

## Context

Trade Scout preserves raw OHLCV, split-adjusted OHLC, cash dividends, and a canonical field named `split_factor`. Provider APIs use similar names for different quantities. In particular, an event-date split ratio (for example 4-for-1) is not the same object as the cumulative multiplier required to transform a historical raw price onto the current split-adjusted share basis.

Massive documents its aggregate `adjusted=true` output as split-adjusted only, and its current Splits endpoint separately exposes a cumulative `historical_adjustment_factor`. Tiingo's EOD `splitFactor` is an event-date factor, while its `adj*` prices incorporate both split and dividend adjustments. Treating these provider fields as interchangeable would silently corrupt adjustment semantics.

## Decision

Within canonical Trade Scout `DailyBar`, `split_factor` means:

> the **cumulative split-only price multiplier applicable to that observation**, such that, subject to provider precision, `close_split_adjusted = close_raw * split_factor` and the same multiplier applies to raw O/H/L.

It does **not** mean the split event ratio occurring on that date.

Consequences:

1. A provider may populate canonical `split_factor` only when it can supply or deterministically establish the cumulative split-only multiplier for the observation.
2. Split event ratios belong in corporate-action records and their preserved source fields.
3. A provider event field called `splitFactor`, `split_from`, `split_to`, or similar must not be copied into canonical `split_factor` merely because the names resemble each other.
4. Dividend-adjusted or total-return-adjusted OHLC must never be labeled as split-adjusted OHLC.
5. If the cumulative split-only multiplier is unavailable, the provider staging record leaves `split_factor` absent and generic canonical normalization quarantines it rather than assuming `1.0`.
6. Secondary-provider reconciliation may still use independently sourced raw OHLCV without promoting that secondary record into research-ready canonical storage.

## Current provider mappings

### Massive

The candidate adapter requests the same daily aggregate window both unadjusted and split-adjusted. Because Massive documents `adjusted=true` as split-adjusted and not dividend-adjusted, the adapter may derive the observation multiplier as adjusted price divided by raw price, subject to consistency checks. The dedicated Splits endpoint remains the corporate-action evidence source.

### Tiingo

Tiingo EOD `splitFactor` is retained as corporate-action evidence only. It is not canonical `split_factor`. Tiingo's `adj*` prices are also not used as Trade Scout split-adjusted OHLC because Tiingo documents its adjustment methodology as incorporating dividends as well as splits. Until a cumulative split-only multiplier is independently established, Tiingo secondary daily bars are raw-validation records and are not eligible for generic canonical promotion.

## Alternatives rejected

- **Define `split_factor` as the event-day split ratio.** Rejected because it is insufficient to reproduce split-adjusted historical prices on arbitrary dates.
- **Assume a missing factor is `1.0`.** Rejected because this silently misstates historical observations before later split events.
- **Use provider total-return adjusted prices.** Rejected because this conflates executable price continuity with dividend reinvestment and violates the project's explicit raw/adjusted separation.

## Verification

Provider adapters and normalization tests must cover this distinction. Any future provider mapping that changes the adjustment definition requires a new adjustment-policy version and, where it changes canonical content, a new immutable dataset version.
