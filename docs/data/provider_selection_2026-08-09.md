# Phase 1 provider-selection decision boundary — 2026-08-09

Status: **ACTIVE EVALUATION — no canonical provider accepted**

Trade Scout's Data Foundation requires provider selection to consider technical coverage **and** the right to preserve raw data, create reproducible derived research artifacts, and retain versioned datasets. Technical API access alone is not acceptance.

## Current provider roles

| Provider | Current role | Reason |
|---|---|---|
| Massive | technically strong candidate, licensing blocked | Existing live evaluation demonstrates useful US-equity reference, corporate-action and price capabilities, but the public individual/market-data terms previously reviewed for this project do not establish the non-display/persistent research rights Trade Scout requires. Do not promote to canonical provider without applicable written rights. |
| Tiingo | secondary technical candidate, licensing blocked pending written approval | EOD coverage and corporate-action fields are useful for independent validation. Current public Terms of Use permit internal API consumption but state that retained Derived Data require express written approval and require deletion of Tiingo Data after subscription termination. This is not sufficient for Trade Scout's immutable long-lived research history without clarification. |
| Alpha Vantage | specialist evaluation source, licensing/entitlement not accepted | Historical `LISTING_STATUS` is useful for survivorship evidence, but current terms classify investment analysis/research/testing beyond personal usage as commercial use, and full daily history is plan-dependent. The observed empty-JSON historical response also remains operational evidence against relying on it as the sole foundation. |
| SEC EDGAR | issuer/reference specialist | Public issuer/reference evidence is useful for reconciliation. CIK remains issuer-level metadata, not permanent security identity; SEC does not supply the required historical OHLCV foundation. |
| EODHD | **next primary-candidate evaluation** | Current public personal-use terms explicitly allow a non-professional user to store, manipulate and analyze data for private non-commercial purposes during an active subscription. The service documents 30+ years of EOD history on paid plans, active/delisted US symbol lists, delisted price history, splits/dividends, ISIN fields where available, and a US symbol-change feed. Storage must be deleted after subscription termination, and commercial/product use requires a separate commercial path. |

## Why EODHD is evaluated next

The project charter says to reduce the uncertainty that blocks the next dependency, prefer simple solutions, make invalid prerequisites fail visibly, and implement narrowly. The largest remaining Phase 1 uncertainty is no longer generic ingestion code; it is whether a provider can satisfy history, survivorship, corporate-action, identity/provenance and licensing requirements together at a tolerable cost.

EODHD is therefore the next candidate to implement behind the existing provider-neutral boundary. This is an **evaluation decision**, not provider acceptance.

## Acceptance constraints for EODHD

EODHD must not be accepted as the primary provider until evidence demonstrates all of the following:

1. Applicable subscription/license permits the exact intended Trade Scout use and retention period.
2. Multi-year US-equity raw OHLCV is reproducible for active and delisted securities.
3. Corporate-action coverage is sufficient to construct Trade Scout's explicit split-only representation without relabeling total-return-adjusted prices.
4. Provider identities can be linked to canonical instruments without treating ticker as permanent identity; ISIN or another durable identifier is preferred where available.
5. Symbol changes and mergers do not create false continuity.
6. Representative values pass independent cross-provider validation.
7. The resulting canonical sample passes quality, point-in-time universe, provenance and storage acceptance gates.

## Scope boundary

Do not begin Phase 2 feature calculations to work around provider uncertainty. The Data Architecture acceptance gate remains authoritative. This document does not weaken the checked-in acceptance ledger and does not authorize redistribution or commercial use of any provider data.

## Official sources reviewed on 2026-08-09

- EODHD Terms and Conditions: personal non-professional users may store, manipulate and analyze information for private non-commercial purposes while subscribed; stored data must be deleted after termination/expiry; commercial use follows a separate path.
- EODHD pricing and historical EOD documentation: paid EOD plans advertise 30+ years of history; free access is limited to the past year.
- EODHD delisted-company documentation: delisted US symbols and their historical EOD/split/dividend data remain queryable.
- EODHD Exchanges API: active/delisted symbol lists include ISIN where available.
- EODHD Symbol Change History: US ticker-renames are documented from 2022-07-22 onward, so this endpoint alone is not sufficient for full historical symbol continuity.
- Tiingo Terms of Use, last updated 2026-07-18: internal API use is allowed, but retained Derived Data require express written approval and source data must be deleted after subscription termination.
- Alpha Vantage Terms of Service: investment analysis, research, testing and monitoring beyond personal usage are categorized as commercial use and require contacting Alpha Vantage.
