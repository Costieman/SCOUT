# Trade Scout — Massive Live Provider Evaluation

**Date:** 2026-08-08  
**Evaluation version:** `massive-live-evaluation-2026-08-08-v2`  
**Status:** Partial pass; provider not accepted

## Purpose

This note records the first execution of the Phase 1 provider-evaluation path against a real Massive API credential. It separates observed runtime evidence from public product documentation and does not convert the candidate-provider hypothesis into a canonical-provider decision.

## Security and execution boundary

The credential was supplied to GitHub Actions as the repository secret `MASSIVE_API_KEY`. Workflow logs showed only the masked secret value. The live runner passed the credential directly to the Massive HTTP client and did not write it into raw manifests or the sanitized evaluation report.

Exact provider response bytes were captured to the ephemeral workflow runtime through `RawBatchStore` before JSON decoding. Only the sanitized JSON evaluation report was uploaded as a workflow artifact; raw vendor bytes were not uploaded.

## Live sample

The evaluation attempted five targeted cases:

| Case | Purpose | Result |
|---|---|---|
| MSFT, 2026-07-27 to 2026-08-07 | Current active equity and repeatable daily-bar retrieval | **PASS** |
| AAPL, 2020-08-03 to 2020-09-04 | Known split and dividend window | **BLOCKED — HTTP 403** |
| TWTR, 2022-10-03 to 2022-10-27 | Inactive/delisted equity | **BLOCKED — HTTP 403** |
| META, 2022-06-09 to 2022-06-17 | Historical ticker-change case | **BLOCKED — HTTP 403** |
| ABNB, 2020-12-10 to 2020-12-18 | IPO/short-history boundary case | **BLOCKED — HTTP 403** |

The targeted reference lookups resolved one stable FIGI-based provider identity for every case. The TWTR reference record was returned as inactive with an end date of 2022-10-31. This is useful evidence for the instrument-master path, but it does not prove that the corresponding historical bars and corporate actions are available under the present entitlement.

## Current-data result

The MSFT case passed the automated provider-neutral gate:

- one exact provider identity was discoverable;
- the provider reported the instrument active as expected;
- ten bounded daily bars were retrieved;
- the repeated bounded request returned identical provider-neutral records;
- no bar fell outside the requested date range or resolved to the wrong provider identity;
- canonical normalization returned `PASS` with ten canonical bars, zero normalization issues, and zero daily-bar quality issues;
- provider health and declared instrument, daily-bar, corporate-action, and delisted-security capabilities passed the top-level checks.

This demonstrates that the concrete Massive adapter can execute the current-data path through the same canonical normalization code used by research-facing data. It does not validate the historical foundation.

## Fractional-volume finding

The first live MSFT attempt exposed a genuine schema assumption: Massive returned a non-integral value in aggregate field `v`. The adapter previously required `v` to be integral and failed rather than coercing it.

Massive's current aggregate documentation defines `v` as a `number`, and its documentation also states that decimal volume values can occur. Trade Scout therefore changed the provider, canonical, research-serving, reconciliation, and Parquet storage contracts to preserve provider-reported volume as a floating-point numeric value rather than rounding it to an integer. Raw response bytes remain the exact audit source.

This is an evidence-driven contract correction, not a data repair.

## Historical-access finding

The four historical test windows from 2020 and 2022 returned HTTP 403 while current 2026 aggregates and reference data were available. Public Massive pricing documentation currently describes the individual stock plans as:

- Basic: 5 API calls per minute and 2 years of historical data;
- Starter: unlimited API calls and 5 years of historical data;
- Developer: unlimited API calls and 10 years of historical data;
- Advanced: unlimited API calls and 20+ years of historical data.

The observed request behavior is consistent with a limited-history entitlement. The workflow does not infer the account plan name from HTTP status alone; it records only that the required historical sample is not accessible with the current entitlement.

For the already-defined 2020/2022 evaluation sample, 5 years is insufficient as of August 2026. Ten years is the minimum advertised depth that reaches all current targeted windows. A full 20+ year research foundation would require deeper entitlement if Massive is ultimately selected.

## Raw preservation evidence

The successful v2 live execution produced 21 immutable raw response manifests in the ephemeral workflow runtime. The live runner deliberately reports the manifest count but does not upload the raw payloads. This confirms that the concrete transport is using the raw-capture path; licensing/storage rights still require explicit confirmation before persistent research storage is accepted.

## Remaining gates

Massive is **not accepted** as the canonical provider. The following remain unresolved:

1. Run the complete historical sample with sufficient data entitlement, including split/dividend, delisted, ticker-history, and IPO-boundary cases.
2. Confirm the intended local raw/canonical storage and research use are permitted by the applicable Massive license/plan.
3. Characterize provider correction/revision behavior by re-running the same historical retrieval at separated times and comparing immutable raw checksums.
4. Resolve first-trade/IPO boundary evidence where the current reference path does not populate `first_trade_date`.
5. Run independent secondary-provider reconciliation on a stratified subset.
6. Run the representative multi-year Parquet/DuckDB benchmark after a primary provider and historical depth are accepted.

Until these gates pass, downstream feature and pattern implementation remains blocked.

## Public Massive sources checked

- Stocks pricing: https://massive.com/pricing?product=stocks
- Stocks Custom Bars: https://massive.com/docs/rest/stocks/aggregates/custom-bars
- Massive changelog: https://massive.com/changelog
- Stocks FAQ: https://massive.com/knowledge-base/categories/stocks

Product capabilities, entitlements, prices, and licensing may change; these must be rechecked at the final provider decision.
