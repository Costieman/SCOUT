# Trade Scout — Massive Licensing Acceptance Gate

**Version:** 0.2  
**Date:** 2026-08-08  
**Status:** **BLOCKED unless an applicable Order Form or written license explicitly permits the intended non-display research use**

## 1. Purpose

Trade Scout cannot accept Massive as its canonical Version 1 market-data provider solely because the API works technically. The intended research workflow requires persistent historical storage, non-display analytics, derived technical features, backtesting, and investment-strategy research. Those rights must be covered by the user's actual Massive agreement.

This note records the licensing gate conservatively. It is a project control, not legal advice.

## 2. Public terms reviewed

Massive's current public legal pages were rechecked on 8 August 2026.

The **Massive for Individuals Terms of Service** state that individual/personal Services are for personal, non-commercial, non-business purposes and direct business/commercial users to contact Massive sales.

The separate **Market Data Terms of Service**, last updated 28 August 2025, are more restrictive for the intended Trade Scout workflow. The public terms state, in substance, that:

- the standard license is limited to personal, non-business, non-commercial use;
- absent a subsequent agreement, Market Data is generally for **display use only**;
- Market Data may not be used for **non-display use** or to create derivative works, including an investment strategy, unless the subscriber is licensed for that use;
- redistribution and third-party transfer are prohibited without permission;
- if the agreement/account terminates, the subscriber must cease using and delete Market Data in their possession.

Relevant current public pages:

- https://massive.com/individuals-terms-of-service
- https://massive.com/legal/market-data-terms-of-service
- https://massive.com/legal/businesses-terms-of-service
- https://massive.com/legal/terms

The applicable contract may differ if the account has a business agreement, exchange entitlement, Order Form, or other written permission. The project therefore must not infer the user's actual licensed rights from the API plan name or from technical access alone.

## 3. Consequence for Trade Scout

The standard public individual terms do **not appear to grant the rights Trade Scout needs** for its planned architecture. In particular, the intended system is designed to:

1. preserve exact raw provider responses for reproducibility;
2. maintain immutable local Parquet/DuckDB historical datasets;
3. retain multiple historical versions to detect corrections;
4. run non-display programmatic analysis;
5. create derived returns, technical/statistical features, pattern/event labels, outcomes, scores, and rankings;
6. backtest and compare investment-strategy definitions; and
7. use validated definitions in a private scanner/ranking workflow.

Those operations go beyond a display-only data use. Therefore:

> **Massive remains blocked as the canonical provider unless the user's applicable agreement expressly permits this storage and non-display analytical use.**

Technical evaluation evidence already collected remains useful for assessing provider capability, but no additional Massive-backed research dataset should be treated as an accepted project input while this gate remains open.

## 4. Questions requiring written confirmation

The provider-acceptance record should contain a written response or applicable contractual provision addressing:

- May the subscriber persist API/flat-file market data locally for long-term historical research, including raw response archives and normalized Parquet copies?
- May multiple historical versions be retained solely to detect provider corrections and reproduce prior research?
- Does the applicable plan permit non-display programmatic analysis for the subscriber's intended use?
- May the subscriber create local derived data such as returns, indicators, volatility measures, pattern labels, event labels, backtest results, scores, and rankings?
- May those derived results be used to research and operate an investment strategy or private security scanner?
- If the current plan does not grant these rights, what Massive product, exchange entitlement, Order Form, or non-display/business license is required?
- What retention/deletion, attribution, audit, device, or raw-data storage restrictions apply?
- Do inactive/delisted data and corporate actions have any different restrictions?

## 5. Provider-decision rule

Massive can advance from **evaluation candidate** to **accepted provider** only if both conditions are satisfied:

1. the technical historical-data acceptance gates pass; and
2. the user's actual license explicitly covers the intended storage, non-display analytics, derived-data, and research workflow.

A deeper historical subscription tier does not by itself close the licensing gate.

If Massive cannot license this use at an acceptable cost, Trade Scout should select another provider rather than weaken reproducibility, survivorship controls, immutable versioning, or research traceability to fit a display-only license.

## 6. Suggested support inquiry

**Subject: Clarification of permitted use for private systematic historical research**

Hello Massive Support,

I am evaluating Massive as the market-data source for a private research system used only for my own investment research and assets. Before relying on the service for this system, I would like to confirm that the intended use is licensed.

The system would download US-equity historical/reference data, preserve raw API responses locally for audit and reproducibility, normalize the data into local Parquet/DuckDB datasets, retain versioned historical snapshots to detect corrections, calculate derived technical/statistical features, run historical backtests and pattern studies, and use validated results in a private scanner/ranking workflow for my own research. I would not redistribute Massive raw data or provide it to third parties.

Could you please confirm whether my current agreement permits this persistent storage and non-display analytical use? In particular, does it permit local raw/canonical retention, creation of derived analytical data, backtesting, and private investment-strategy/scanner research? If not, please advise which product, agreement, or non-display/business license is required and whether any retention or deletion restrictions would apply.

Thank you.

## 7. Acceptance evidence

When clarification is received, record only the decision-relevant permission/constraints and the date/source of that permission. Do not commit credentials, private billing information, or unrelated correspondence.

Until then, the project should continue with provider-neutral code and alternative-provider evaluation rather than treating Massive market data as licensed research input.
