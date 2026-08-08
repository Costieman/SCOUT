# Alpha Vantage Candidate Adapter

**Status:** evaluation only — not an accepted canonical provider.

## Why it is being evaluated

Alpha Vantage's `LISTING_STATUS` utility is unusually relevant to Trade Scout because it can return active or delisted US stocks and ETFs for historical dates later than 2010-01-01. This directly tests one of the project's hardest requirements: point-in-time universe reconstruction without projecting today's surviving universe backward.

The adapter therefore treats Alpha Vantage as a serious candidate for the **universe/status role**, while keeping the canonical-provider decision open.

## Important entitlement correction

The current Alpha Vantage documentation distinguishes `TIME_SERIES_DAILY` output sizes:

- `compact`: latest approximately 100 observations; available to free and premium keys;
- `full`: complete available history; currently documented as requiring a premium key.

Accordingly, the adapter does **not** assume that a free API key supplies 20+ years of daily OHLCV. Long-history retrieval is disabled by default and can only be enabled with `allow_full_history=True` after the account entitlement has been verified.

This matters because provider evaluation must distinguish a vendor's total database depth from what the selected plan actually permits us to retrieve.

## Implemented evaluation capabilities

- `LISTING_STATUS` active snapshot.
- `LISTING_STATUS` delisted snapshot.
- Historical `LISTING_STATUS(date=...)` for dates later than 2010-01-01.
- Raw `TIME_SERIES_DAILY` CSV retrieval for explicit symbols.
- Compact versus full-output gating.
- Immutable raw-byte capture through the existing `RawBatchStore` when `raw_root` is supplied.
- Explicit API/rate-limit error detection when Alpha Vantage returns JSON instead of the expected CSV.

## Capabilities deliberately not claimed

### Permanent identity / symbol history

`LISTING_STATUS` exposes a symbol, name, exchange, asset type, IPO date, delisting date, and status. It does not, by itself, provide the kind of permanent security identifier supplied by CRSP PERMNO or the standardized identifiers available from some other vendors.

The evaluation adapter therefore uses a symbol-derived **staging** provider ID only so records can cross the adapter boundary. This value must never become Trade Scout's canonical permanent `instrument_id` without an independently validated identity-resolution process. SEC CIK/reference data may help, but ticker reuse, reorganizations, multiple share classes, and entity/security distinctions still require explicit testing.

### Corporate actions

Alpha Vantage exposes adjusted-data and corporate-action-related products, but corporate actions are not declared supported by this adapter yet. Splits, dividends, symbol changes, mergers, and delisting-return behavior require a dedicated validation gate before they can support canonical research.

### Adjustment policy

Only raw `TIME_SERIES_DAILY` is currently declared. `TIME_SERIES_DAILY_ADJUSTED` is a premium endpoint and must not be silently substituted for executable/raw prices.

## Acceptance questions for the live evaluation

1. Does historical `LISTING_STATUS` reconstruct known active/delisted cases correctly across 2010-present?
2. How are ticker changes, ticker reuse, mergers, relistings, ETFs, preferreds, and unusual security types represented?
3. Can SEC EDGAR data resolve identity gaps without introducing hindsight or entity/security confusion?
4. Does the selected Alpha Vantage plan permit the historical OHLCV depth required for the first research program?
5. Are raw daily bars complete and reproducible for active and delisted names?
6. Are split/dividend/corporate-action products sufficient and transparent enough for controlled adjustment construction?
7. What rate limits apply in practice to the selected key, and is a broad historical backfill operationally realistic?
8. Do Alpha Vantage's terms permit the immutable local raw/canonical research storage required by Trade Scout?

## Current interpretation

Alpha Vantage remains worth evaluating, but the strongest free capability identified so far is **historical listing/delisting reconstruction**, not a confirmed free full-history OHLCV database. That distinction should remain explicit until the live and licensing gates are complete.
