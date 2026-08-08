# Trade Scout — Massive Licensing Acceptance Gate

**Version:** 0.1  
**Date:** 2026-08-08  
**Status:** Open acceptance gate — written clarification required

## 1. Purpose

Trade Scout cannot accept Massive as its canonical Version 1 market-data provider solely because the API works technically. The intended research workflow must also be licensed for the actual use being built: persistent historical storage, non-display analytics, derived technical features, backtesting, and investment-strategy research for the subscriber's own use.

This note records the licensing question without interpreting the contract more broadly than its text supports.

## 2. Current public terms reviewed

Massive's current public legal pages reviewed on 8 August 2026 state that products labeled for individual use are for personal, individual, non-business, non-commercial use. The separate Market Data Terms grant a limited personal/non-business/non-commercial license and state that Market Data is generally for display use unless another agreement provides otherwise.

The Market Data Terms also prohibit non-display use or creation of derivative works, including an investment strategy, unless the subscriber is licensed for that use. The terms further distinguish Non-Professional from Professional use and direct users who may not qualify for individual/non-professional use to contact Massive.

Relevant current pages:

- https://massive.com/individuals-terms-of-service
- https://massive.com/legal/market-data-terms-of-service
- https://massive.com/legal/businesses-terms-of-service
- https://massive.com/legal/terms

The project must recheck the applicable terms at the time of provider acceptance because Massive may change them or provide a different Order Form or written permission.

## 3. Intended Trade Scout use requiring clarification

Trade Scout is currently designed to do all of the following for the subscriber's own research environment:

1. Download historical US-equity reference data, OHLCV, corporate actions, symbol history, and inactive/delisted-security records through the API.
2. Preserve exact raw provider responses locally for reproducibility and audit, subject to licensing.
3. Normalize those records into immutable local Parquet datasets with a DuckDB metadata registry.
4. Retain historical dataset versions and checksums so provider revisions can be detected rather than silently overwritten.
5. Calculate local technical and statistical derived data such as returns, ranges, trend measures, volatility measures, and later research features.
6. Backtest pattern/event definitions over historical data.
7. Compare candidate research definitions and estimate conditional outcomes.
8. Use validated definitions in a personal scanner/ranking system that identifies securities for further review.
9. Use the system only for the subscriber's own research/trading decisions unless a later license explicitly permits wider use.
10. Not redistribute Massive raw market data to third parties or expose it publicly.

These intended operations include persistent storage and non-display analytical use. They therefore require explicit licensing confirmation before the project treats Massive as accepted.

## 4. Questions requiring written confirmation

The provider-acceptance record should contain a written response from Massive addressing these questions:

- May an individual subscriber persist API/flat-file market data locally for long-term personal historical research, including raw response archives and normalized Parquet copies?
- May the subscriber retain multiple historical versions solely to detect provider corrections and reproduce prior research?
- Does the applicable plan permit non-display programmatic analysis of the data for the subscriber's own account?
- May the subscriber create local derived data such as returns, technical indicators, volatility measures, pattern labels, event labels, backtest results, scores, and rankings?
- May those derived results be used to research and operate an investment strategy or personal security scanner for the subscriber's own assets?
- If the standard individual plan does not grant these rights, what Massive product, exchange entitlement, Order Form, or non-display/business license would be required?
- Are there retention, deletion, audit, attribution, device, or raw-data storage restrictions that Trade Scout must implement?
- Are inactive/delisted data and corporate actions subject to any different storage or non-display restrictions?

## 5. Provider-decision rule

**Massive remains an evaluation candidate until this gate is closed.**

A deeper historical plan must not be treated as sufficient merely because it unlocks more years of data. The provider decision requires both:

1. technical acceptance of the historical sample and ingestion/reproducibility tests; and
2. licensing that explicitly covers the intended storage and non-display research workflow.

If the applicable Massive license cannot support the intended workflow at an acceptable cost, Trade Scout should evaluate the next provider rather than weaken reproducibility, survivorship controls, or research traceability to fit the license.

## 6. Suggested support inquiry

Subject: Clarification of permitted use for personal systematic historical research

Hello Massive Support,

I am evaluating Massive as the market-data source for a private research system used only for my own investment research and assets. Before purchasing a deeper historical plan, I would like to confirm that the intended use is licensed.

The system would download US-equity historical/reference data, preserve raw API responses locally for audit and reproducibility, normalize the data into local Parquet/DuckDB datasets, retain versioned historical snapshots to detect corrections, calculate derived technical/statistical features, run historical backtests and pattern studies, and use validated results in a private scanner/ranking workflow for my own research. I would not redistribute Massive raw data or provide it to third parties.

Could you please confirm whether this storage and non-display analytical use is permitted under an individual Stocks plan? In particular, does the plan permit local raw/canonical retention, creation of derived analytical data, backtesting, and personal investment-strategy/scanner research? If not, please advise which product, agreement, or non-display/business license is required and whether there are retention or storage restrictions I should design around.

Thank you.

## 7. Acceptance evidence

When clarification is received, store only the decision-relevant summary and permitted-use constraints in project documentation. Do not commit account credentials, private billing information, or unrelated correspondence.
