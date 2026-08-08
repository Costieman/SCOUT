# Trade Scout — Alpha Vantage + SEC EDGAR Complementary Data Architecture

**Version:** 0.1  
**Date:** 2026-08-08  
**Status:** Phase 1 evaluation design; no provider accepted

## Purpose

This note defines a narrow evaluation architecture for combining Alpha Vantage and SEC EDGAR without allowing either source to bypass Trade Scout's canonical-data, provenance, point-in-time, or provider-isolation rules.

The design is intentionally conservative. Alpha Vantage is being evaluated for historical listing-state reconstruction and daily market data. SEC EDGAR is treated as an independent public reference/fundamentals source. Neither source becomes analytical truth merely because it is free or convenient.

## Roles

### Alpha Vantage candidate role

Evaluate Alpha Vantage for:

- point-in-time US listing snapshots through `LISTING_STATUS`;
- active and delisted symbol discovery from 2010 onward;
- recent/raw daily OHLCV through `TIME_SERIES_DAILY`;
- possible longer daily history only after entitlement is verified;
- possible corporate-action fields only after explicit adjustment/action validation.

Alpha Vantage must not be used as Trade Scout's permanent identity system unless a stable identity solution is independently demonstrated. Ticker is not a permanent identifier.

### SEC EDGAR complementary role

Evaluate SEC EDGAR for:

- issuer identity anchored to SEC CIK;
- company-name and filing-history evidence;
- exchange/ticker metadata available in SEC submissions/reference data;
- filing and XBRL fundamentals where later research requires them;
- independent investigation of issuer reorganizations, mergers, name changes, and similar lifecycle events.

SEC EDGAR is not a daily market-price provider and therefore cannot replace the OHLCV source.

## Canonical boundary

Provider-native records terminate at the adapter/staging layer. Downstream Trade Scout modules consume only canonical contracts.

The canonical instrument master owns:

- immutable Trade Scout `instrument_id`;
- dated symbol assignments;
- exchange history where supported;
- security classification;
- provider identifiers such as CIK and vendor-specific IDs;
- first reliable observation and delisting/terminal state;
- provenance and reconciliation decisions.

A provider's ticker must never be used as the canonical instrument key.

## Identity reconciliation policy

CIK is useful but must not be treated as equivalent to a security identifier. A single issuer can have multiple listed securities or share classes, and corporate reorganizations may alter the economic security while leaving related issuer history.

Trade Scout therefore distinguishes:

1. issuer identity — e.g. SEC CIK;
2. security identity — Trade Scout `instrument_id`;
3. symbol assignment — dated ticker/exchange record;
4. provider identity — provider-native key or symbol-derived staging key;
5. corporate-event linkage — explicit evidence connecting old and new records.

Automatic merges are allowed only when evidence is sufficiently strong and deterministic. Ambiguous cases remain unresolved and visible rather than being silently joined.

## Point-in-time universe design

For a historical date `t`, the universe constructor should begin from a dated listing snapshot, not today's surviving list.

Candidate sequence:

1. request Alpha Vantage active and delisted listing state as of `t`;
2. normalize security type and exchange fields;
3. reconcile symbols to canonical instruments using only evidence known at or before the reconstruction policy permits;
4. apply Version 1 security-type exclusions;
5. join trailing price/liquidity history using canonical instrument identity;
6. apply price, liquidity, age, and data-quality filters using trailing information only;
7. persist the resulting universe version and provenance.

SEC data may strengthen identity/reference reconciliation but must not inject later-known facts into a historical eligibility decision unless the field is explicitly allowed as timeless reference metadata.

## Alpha Vantage acceptance gates

Alpha Vantage may advance as a serious Phase 1 source only if the live evaluation demonstrates:

- historical `LISTING_STATUS` snapshots are available and structurally coherent across multiple dates;
- delisted records remain discoverable rather than disappearing from historical reconstruction;
- exchange and asset-type coverage is adequate for the Version 1 US common-stock universe;
- recent raw daily bars are reproducible;
- request/rate-limit behavior is operationally manageable;
- full-history entitlement is characterized rather than assumed;
- licensing permits the intended local raw/canonical research storage;
- corporate actions and adjustment semantics are either validated or explicitly supplied by another approved source;
- identity limitations have a defensible reconciliation solution.

Failure of a critical gate results in `REJECT` or `ACCEPT WITH LIMITATIONS`, not silent compensation by another criterion.

## SEC EDGAR acceptance gates

Because SEC EDGAR is a complementary source, the gates differ:

- automated access must follow SEC fair-access requirements;
- requests identify Trade Scout through a configured User-Agent/contact value;
- CIK/ticker/name/reference data can be persisted with provenance;
- bulk or bounded retrieval is deterministic enough for reproducible snapshots;
- issuer-level metadata is never mistaken for security-level identity;
- later filing amendments/revisions create new source observations rather than rewriting prior research provenance.

No SEC API key is required for public read access; the operational configuration should contain a descriptive User-Agent/contact value, not a secret credential.

## Evaluation dataset

The initial joint evaluation should remain deliberately small and auditable.

### Listing-state dates

Use multiple dates spanning different market eras, including at least:

- 2011/2012 early supported history;
- 2014;
- 2020/2021;
- 2022/2023;
- current/latest.

### Identity/lifecycle cases

Include examples of:

- long-lived active securities;
- ticker changes;
- acquisitions/delistings;
- bankrupt/delisted issuers;
- recent IPOs;
- multiple share classes where possible;
- excluded security types such as ETFs or preferred shares.

The manifest records why each case exists. Event-targeted cases test known failure modes; a random component reduces clean-case selection bias.

## Reconciliation output

Each evaluated case should produce a machine-readable record containing:

- evaluation case ID;
- as-of date;
- Alpha Vantage symbol/status record;
- SEC CIK/reference match candidates;
- canonical security match state;
- confidence/evidence notes;
- unresolved ambiguity flags;
- daily-bar availability window;
- corporate-action evidence status;
- data-quality result;
- raw-source checksums/provenance references.

Suggested match states:

- `MATCHED_STRONG` — deterministic evidence supports the security mapping;
- `MATCHED_PROVISIONAL` — useful mapping but evidence is incomplete;
- `AMBIGUOUS` — multiple plausible candidates;
- `UNMATCHED` — no defensible match;
- `NOT_APPLICABLE` — issuer mapping not required for the case.

Only `MATCHED_STRONG` should be eligible for automatic canonical identity creation during the first backfill.

## Decision outcomes

After the bounded live evaluation, Alpha Vantage should receive one of four decisions:

- `ACCEPT_PRIMARY_CANDIDATE` — sufficiently strong to proceed to representative backfill and secondary validation;
- `ACCEPT_SPECIALIST_SOURCE` — useful for listing/universe reconstruction but not adequate as canonical OHLCV source;
- `ACCEPT_WITH_LIMITATIONS` — usable only with explicit complementary providers/constraints;
- `REJECT` — critical research-integrity or licensing requirements fail.

SEC EDGAR is expected to be evaluated independently as a complementary reference source rather than competing for the primary price-provider role.

## Scope boundary

This work does not begin Feature Engine, Pattern Engine, breakout research, or scanner implementation. The output of this phase is a trustworthy, versioned historical data foundation that later analytical modules can safely consume.
