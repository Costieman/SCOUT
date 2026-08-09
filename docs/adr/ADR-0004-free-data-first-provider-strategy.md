# ADR-0004: Free-data-first provider strategy

Status: Accepted
Date: 2026-08-09

## Context

Trade Scout Phase 1 requires a trustworthy historical data foundation, but Version 1 must not require a paid market-data subscription. The existing provider-neutral architecture is intentionally designed so vendor-specific behavior terminates at adapters and downstream research consumes canonical Trade Scout contracts.

The Data Architecture specification still governs: one canonical source of truth per research dataset; secondary sources validate rather than get blended; point-in-time correctness, immutable raw preservation where permitted, explicit quality states, provenance, and versioning remain mandatory. The Provider Interface specification likewise requires unsupported capabilities to fail explicitly.

Free sources have complementary rather than identical strengths. SEC EDGAR is free and suitable for issuer identity/reference evidence but is not an OHLCV provider. Alpha Vantage exposes historical listing/delisting status back to 2010, but its free daily OHLCV access is constrained and therefore cannot be assumed to provide representative full-history price backfills. Stooq is a candidate free historical OHLCV source, but its provenance, adjustment semantics, inactive/delisted coverage, correction behavior, and redistribution/licensing terms must be characterized before canonical acceptance.

## Decision

Phase 1 becomes **free-data-first**.

1. No paid provider is required to complete the initial usable Trade Scout build.
2. EODHD remains an optional future/premium provider adapter and evidence path; it is not a prerequisite for the free Version 1 data foundation.
3. The free provider stack will be evaluated as complementary roles rather than pretending one source supplies every field:
   - **SEC EDGAR**: issuer identity/reference and historical filing metadata where useful.
   - **Alpha Vantage**: historical active/delisted universe evidence via LISTING_STATUS and bounded validation/evaluation calls within free entitlements.
   - **Stooq**: candidate primary historical daily OHLCV source, subject to explicit acceptance testing.
   - Additional genuinely free sources may be evaluated as secondary validators without changing downstream contracts.
4. Canonical research datasets may be assembled from multiple specialist source families only when each canonical field has one declared authoritative source and provenance. Values from competing OHLCV feeds are never averaged or silently blended.
5. If a free source cannot support a requirement, Trade Scout records the capability as unsupported/partial and narrows the free research claim rather than fabricating completeness.
6. Phase 1 acceptance for the free edition will distinguish **core scientific requirements** from **provider-limited enhancements**. Point-in-time eligibility, immutable versioning, quality controls, explicit adjustment semantics, and vendor-independent downstream contracts remain non-negotiable. Exact delisting returns or complete historical corporate-action metadata may remain unavailable when free sources cannot supply them; affected analyses must expose that limitation.
7. A future paid-data edition must enter through the same ProviderAdapter boundary and must not change feature, pattern, event, outcome, risk, scanner, or UI scientific meaning merely because the vendor changes.

## Consequences

The substantial Phase 1 architecture already implemented remains useful. Raw preservation, normalization, quality gates, instrument identity, dataset versioning, point-in-time universe construction, serving contracts, evidence registration, checkpointing, and provider acceptance machinery are retained.

The immediate engineering priority changes from running a paid EODHD representative campaign to evaluating and implementing a free-data stack. Existing EODHD code remains isolated and tested but should not block Phase 1 free-edition progress.

The free edition may have a narrower historical research claim than a future premium edition. Any such difference must be visible in dataset capabilities and experiment provenance. Research conclusions from materially different datasets remain separate evidence and are not pooled without explicit validation.

## Acceptance implications

Before a free OHLCV source becomes canonical, it must demonstrate, to the extent its public access permits:

- reproducible historical retrieval;
- explicit raw/adjusted semantics;
- deterministic normalization;
- sufficient historical depth for the first research program;
- stable symbol/query mapping;
- missing/duplicate/impossible-bar quality behavior;
- documented inactive/delisted limitations;
- documented licensing/redistribution constraints;
- representative storage/query performance;
- successful consumption through the existing vendor-independent ResearchBar contract.

Where a requirement cannot be demonstrated with free data, the limitation is recorded and the corresponding research scope is reduced rather than silently waived.
