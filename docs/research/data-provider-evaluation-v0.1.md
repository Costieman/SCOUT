# Trade Scout — Data Provider Evaluation

**Version:** 0.1  
**Date:** 2026-08-08  
**Status:** Evaluation baseline — no provider accepted yet

## 1. Purpose

This document narrows the Phase 1 provider decision without prematurely coupling Trade Scout to a vendor. The governing data specifications require one primary canonical provider and at least one independent secondary source used for validation rather than indiscriminate blending.

The decision is intentionally evidence-gated. Public documentation is sufficient to identify candidates, but it is not sufficient to accept a provider. Acceptance requires a reproducible sample backfill through the Trade Scout provider boundary and explicit characterization of historical coverage, inactive/delisted securities, corporate actions, symbol/identifier history, adjustment behavior, corrections, API reliability, licensing, and cost.

## 2. Version 1 requirements

A primary provider must support the following well enough for defensible US-equity research:

1. Daily historical OHLCV over a multi-regime period.
2. Active and inactive/delisted US-listed common equities.
3. Corporate actions sufficient to distinguish genuine price movement from splits, dividends, mergers, and related discontinuities.
4. Stable identifiers and/or enough dated reference information to build a permanent Trade Scout `instrument_id` mapping without treating ticker as identity.
5. Raw or explicitly characterized unadjusted prices plus transparent split-adjustment behavior.
6. Reproducible historical retrieval and deterministic incremental updates.
7. Correction/revision behavior that can be detected and versioned.
8. Licensing compatible with local research storage and the intended use of Trade Scout.
9. Operationally reasonable API/bulk reliability, limits, and cost.

A secondary provider does not need to reproduce every primary-provider capability. It must provide sufficiently independent OHLCV/corporate-action evidence to confirm anomalies and investigate disagreements.

## 3. Public-documentation screen

### Massive — primary evaluation candidate

Public documentation currently indicates:

- all US stock tickers, reference data, and corporate actions are available across the stock plans;
- inactive/delisted tickers can be requested through the ticker reference endpoint;
- ticker overview records expose standardized identifiers including CIK, Composite FIGI, and Share Class FIGI;
- both adjusted and unadjusted stock-price views are available through REST, while stock flat files are explicitly unadjusted;
- dedicated split and dividend endpoints exist;
- ticker-event history can expose symbol changes, but that endpoint is explicitly experimental;
- current individual historical-depth tiers range from 2 years on the free plan through 20+ years on the Advanced plan.

**Assessment:** best current primary evaluation candidate because the documented combination of inactive securities, dated reference data, standardized identifiers, raw/adjusted handling, and corporate actions most closely matches Trade Scout's canonical-data requirements. The experimental ticker-event endpoint is a material risk and must not be assumed sufficient for complete historical symbol continuity until tested.

**Decision:** evaluate first; do not purchase the deepest tier until the sample gate demonstrates that the required historical identity and corporate-action coverage are adequate.

### Tiingo — secondary validation candidate

Public documentation currently indicates:

- 30+ years of end-of-day price history on the individual plans;
- both raw and adjusted price fields;
- proprietary error checking intended to detect missing prices/corporate actions and exchange-listing changes;
- a low-cost individual Power tier with high API limits;
- current symbology documentation states that permaticker and delisted-ticker support is still being expanded.

**Assessment:** attractive independent secondary source for OHLCV and corporate-action validation. The stated limitations around delisted/permanent symbology make it weaker as the canonical Version 1 identity source.

**Decision:** evaluate as the first secondary validation candidate.

### EODHD — lower-cost fallback candidate

Public documentation currently indicates:

- 30+ years of end-of-day coverage;
- explicit delisted-symbol retrieval;
- US symbol-change history;
- a low-cost end-of-day plan;
- importantly, delisted securities before 2018 are documented as having EOD data only, while dividends/splits/fundamentals are available for delistings after 2018.

**Assessment:** useful fallback and potentially useful cross-source check, but the documented pre-2018 corporate-action limitation for delisted securities is a material weakness for the long-horizon survivorship-aware canonical dataset.

**Decision:** retain as fallback/tertiary evaluation candidate rather than the first canonical choice.

## 4. Evaluation matrix

The following criteria are acceptance gates rather than marketing-score weights. A provider that fails a critical scientific-integrity requirement cannot compensate by being cheaper or faster.

| Criterion | Critical? | Evidence required from sample evaluation |
|---|---:|---|
| Historical daily OHLCV depth | Yes | Requested ranges returned without unexplained truncation |
| Inactive/delisted coverage | Yes | Delisted sample discoverable and retrievable |
| Delisting/status metadata | Yes | Dated status/end information characterized |
| Stable identity/reference fields | Yes | Provider IDs and standardized identifiers can be mapped without ticker-as-identity |
| Symbol-change history | Yes | Known rename/reorganization cases reconstruct correctly or limitation is explicitly solved elsewhere |
| Split coverage | Yes | Known split events agree with observed discontinuities |
| Dividend coverage | Important | Cash-dividend fields/events present and dated consistently |
| Raw/unadjusted OHLCV | Yes | Exact unadjusted representation available and documented |
| Adjustment transparency | Yes | Split-adjusted behavior reproducible from documented factors/events |
| Correction/revision behavior | Yes | Re-fetch/revision behavior can be detected and versioned |
| API/bulk determinism | Yes | Repeated bounded request gives equivalent logical records |
| Pagination/rate-limit behavior | Operational | Checkpoint/retry path can be implemented safely |
| Licensing/storage | Yes | Local raw/canonical persistence permitted for intended use |
| Cost | Operational | Cost characterized only after scientific gates pass |
| Support/operational stability | Operational | Failure modes and support path documented |

## 5. Required sample design

The first evaluation dataset should remain small enough to inspect manually but deliberately stress the cases that create research bias.

### Event-targeted cases

- long-lived active common stocks with known split histories;
- dividend-paying active stocks;
- securities with historical ticker changes;
- securities delisted before 2018;
- securities delisted after 2018;
- recent IPOs with short trading histories;
- securities near merger/acquisition or other identity-changing events;
- examples of excluded security types so classification behavior can be checked.

### Stratified random cases

Add a small random sample across:

- NYSE, Nasdaq, and NYSE American;
- high, medium, and lower eligible liquidity;
- multiple decades where provider depth permits;
- active and inactive status.

The sample manifest must record why each instrument/date range was included. Hand-selected event cases test known failure modes; the random component reduces the risk of evaluating only clean examples.

## 6. Sample acceptance tests

A candidate primary provider advances only if the evaluation can demonstrate:

1. **Reference completeness:** instruments can be discovered with enough metadata to distinguish security type, exchange, active/inactive state, and stable identity candidates.
2. **Ticker independence:** historical identity is not reconstructed by assuming a ticker uniquely identifies one economic security forever.
3. **OHLCV integrity:** bounded raw daily requests are reproducible and pass the initial Trade Scout structural/market-logic checks or produce explainable quality events.
4. **Corporate-action consistency:** known split discontinuities are explained by provider events/factors rather than appearing as unexplained returns.
5. **Delisted inclusion:** inactive securities remain available in the historical sample and are not silently excluded from retrieval.
6. **Adjustment transparency:** raw and adjusted representations can be distinguished and the provider's adjustment policy is characterized.
7. **Revision detectability:** the same logical retrieval can be re-run with raw payload/checksum preservation so historical corrections produce a new ingestion/version event rather than a silent rewrite.
8. **Provider isolation:** all provider-native fields terminate at the adapter/staging boundary; the test downstream consumer sees only canonical Trade Scout contracts.

## 7. Initial decision

**Primary evaluation candidate:** Massive.  
**Secondary validation candidate:** Tiingo.  
**Fallback/tertiary candidate:** EODHD.

This is not final provider acceptance. The ordering is a hypothesis based on public capability documentation. It becomes an accepted project decision only after the provider-evaluation dataset passes the gates above and licensing is confirmed for the intended storage/use model.

## 8. Immediate implementation consequence

The next code slice should build the provider-evaluation harness around the already accepted `ProviderAdapter` boundary rather than hard-code Massive-specific objects into the canonical layer. A Massive adapter may then be implemented as the first concrete adapter when credentials are available. The same harness must be reusable for Tiingo and EODHD so the comparison tests the providers rather than three different ingestion implementations.

## 9. Public sources consulted

- Massive Stocks REST API overview, ticker reference, corporate-action, aggregate, flat-file, and pricing documentation (accessed 2026-08-08).
- Tiingo pricing, end-of-day API, and symbology documentation (accessed 2026-08-08).
- EODHD pricing, historical EOD, delisted-company, and US symbol-change documentation (accessed 2026-08-08).

Exact product capabilities, pricing, licensing, and endpoint status are time-varying. They must be rechecked at the point of purchase or production acceptance.
