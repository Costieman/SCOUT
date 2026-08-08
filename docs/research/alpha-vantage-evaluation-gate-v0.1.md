# Trade Scout — Alpha Vantage Evaluation Gate

**Version:** 0.1  
**Date:** 2026-08-08  
**Status:** candidate evaluation — no provider acceptance

## 1. Why this gate exists

Alpha Vantage deserves a separate evaluation because its `LISTING_STATUS` endpoint addresses a requirement that many low-cost price providers handle poorly: reconstruction of active and delisted US stocks/ETFs as of historical dates. The public documentation states that dated queries are supported for dates later than 2010-01-01.

That capability could materially improve Trade Scout's 2010-present point-in-time universe construction. It does not, however, resolve the entire canonical-data problem.

## 2. Important correction to the earlier free-data assumption

The provider's current documentation states that `TIME_SERIES_DAILY` supports `compact` and `full` output. `compact` is available to free and premium keys and returns the latest approximately 100 observations. `full` is the complete-length output and is currently documented as a premium capability.

Therefore, **Trade Scout must not treat Alpha Vantage as a confirmed free 20+ year OHLCV source.** The database may have that depth, but access to the complete daily history is a separate entitlement question.

This changes the evaluation framing:

- `LISTING_STATUS`: potentially strong free point-in-time universe/status source;
- recent daily raw OHLCV: useful for bounded evaluation and possibly secondary validation;
- full historical OHLCV: potentially useful, but cost/entitlement must be measured rather than assumed;
- adjusted daily data: premium and requires separate adjustment-policy validation.

## 3. Scientific gates

Alpha Vantage advances only if the following are demonstrated rather than inferred from marketing documentation.

### Gate A — point-in-time listing reconstruction

Run historical snapshots across multiple dates from 2010-present and verify:

- active/delisted counts are plausible;
- NYSE, Nasdaq, and NYSE American coverage is represented;
- known delisted securities remain discoverable;
- IPO and delisting dates behave consistently around lifecycle boundaries;
- ETFs and excluded security types can be distinguished from Version 1 common equities.

### Gate B — permanent identity

`LISTING_STATUS` does not expose a CRSP-like permanent security identifier. Trade Scout must therefore test whether SEC EDGAR/reference data can resolve identity without relying on ticker permanence.

Stress cases must include:

- ticker changes such as FB -> META;
- ticker reuse by unrelated companies;
- mergers/acquisitions;
- multiple share classes;
- relistings/reorganizations;
- company/entity identity versus exchange-listed security identity.

Failure to solve this cleanly prevents Alpha Vantage from being the sole canonical identity source even if listing history is excellent.

### Gate C — historical OHLCV entitlement and depth

Determine what the selected API key actually permits:

- compact versus full `TIME_SERIES_DAILY`;
- oldest retrievable daily bar;
- active versus delisted price retrieval;
- reproducibility of repeated bounded requests;
- practical request budget and backfill throughput.

No full-universe backfill begins before this is measured.

### Gate D — corporate actions and adjustments

Validate splits, dividends, adjustment fields, and corporate-action endpoints against known events. Trade Scout must be able to preserve raw prices and construct/characterize split-consistent series without silently accepting an opaque adjusted field.

### Gate E — licensing and storage

Confirm that the selected Alpha Vantage plan permits the intended use:

- local systematic research;
- immutable raw response preservation where needed;
- canonical Parquet/DuckDB storage;
- reproducible historical experiments;
- routine end-of-day updates.

This is a hard gate. Technical access alone is insufficient.

## 4. SEC EDGAR role

SEC EDGAR remains a free specialist source for issuer/company reference data, filing history, historical names and tickers where available, and CIK-based entity identity. It is not a daily OHLCV source.

A likely architecture to test is therefore:

`Alpha Vantage LISTING_STATUS` + `SEC EDGAR identity/reference` + `canonical Trade Scout instrument master` + `separate canonical/validation OHLCV decision`.

This should be treated as an empirical integration hypothesis, not accepted architecture, until ticker/security/entity edge cases are tested.

## 5. Bounded live run

The repository contains `scripts/run_alpha_vantage_live_evaluation.py`. The first live run intentionally uses approximately ten API requests:

- four point-in-time/latest listing snapshots, each requesting active and delisted states;
- two recent compact daily-bar samples.

The run preserves raw responses locally and emits a JSON/Markdown report. It does not upload the API key or raw market payloads to Git.

## 6. Decision states

- **ACCEPT — universe/status role:** historical listing reconstruction is sufficiently reliable for point-in-time universe work.
- **ACCEPT — broader candidate role:** additionally passes historical OHLCV, adjustment, identity-integration, and licensing gates.
- **ACCEPT WITH LIMITATIONS:** useful specialist/secondary source but not sufficient as canonical provider.
- **REJECT:** fails scientific, operational, or licensing requirements.

No decision should be upgraded solely because the API is free.

## 7. Public documentation checked

- Alpha Vantage API Documentation — `LISTING_STATUS`, `TIME_SERIES_DAILY`, and `TIME_SERIES_DAILY_ADJUSTED`, accessed 2026-08-08: https://www.alphavantage.co/documentation/
- SEC EDGAR API documentation is evaluated separately as a specialist reference/identity source.

Product entitlements and terms are time-varying and must be rechecked before purchase or production acceptance.
