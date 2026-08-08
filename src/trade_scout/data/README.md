# Data module

## Purpose

The data module owns provider isolation, canonical market-data contracts, permanent instrument identity, immutable raw preservation, provenance, validation, and the serving boundary consumed by later research modules.

## Explicit non-responsibilities

This module does not calculate technical features, detect patterns/events, evaluate outcomes or stops, rank candidates, issue alerts, or silently repair suspicious market data.

## Completed Phase 1 slices

The data foundation now establishes:

- permanent internal `InstrumentId` and canonical instrument/symbol-history contracts;
- deterministic initial `InstrumentId` derivation from the first admitted non-ticker provider identity;
- explicit linking of additional provider identities without ticker matching;
- point-in-time dated symbol resolution with overlap/conflict detection;
- unresolved symbol records retained as unresolved rather than guessed from matching tickers;
- exact raw payload persistence before normalization, with SHA-256 checksum and immutable batch manifests;
- idempotent identical raw retries and explicit conflict if a batch ID is reused with different content;
- rejection of credential-like request parameters before a raw manifest can be written;
- timezone-aware retrieval provenance and provider revision metadata;
- canonical raw and split-adjusted daily-bar representation;
- explicit `PASS`, `WARN`, `QUARANTINE`, and `REJECT` quality states;
- a vendor-neutral `ProviderAdapter` protocol and capability declaration;
- provider-neutral staging records for instruments, symbols, bars, and corporate actions;
- deterministic structural/market-logic checks for daily bars;
- a stable `ResearchBar` serving contract that never silently changes price representation.

## Identity rule

Ticker is display/history metadata, not identity. The first canonical instrument ID is seeded from the primary provider's stable instrument identity and thereafter becomes an opaque Trade Scout key. A second provider must be explicitly linked to that existing key. The system does not merge records merely because ticker, name, or exchange look similar.

This bootstrap rule supports deterministic reconstruction from the same primary-provider identity while preserving the ability to attach additional provider IDs later. Provider replacement therefore requires preserving or explicitly migrating the instrument master; it must not silently regenerate identity from a new ticker list.

## Raw-zone rule

Raw vendor bytes are stored before normalization whenever licensing permits. A raw batch contains an exact payload and a machine-readable manifest recording provider, endpoint/product name, non-secret request parameters, timezone-aware retrieval timestamp, checksum, content length, and optional provider revision. Existing batches are never overwritten. A corrected provider response must receive a new batch identity.

Runtime raw data belong outside Git; tests use temporary directories only.

## Provider evaluation direction

The Phase 1 public-documentation screen is recorded in [`docs/research/data-provider-evaluation-v0.1.md`](../../../docs/research/data-provider-evaluation-v0.1.md). Massive is the first primary-provider evaluation candidate, Tiingo is the first secondary-validation candidate, and EODHD is retained as a fallback/tertiary candidate.

This ordering is not provider acceptance. The primary source must still pass a small reproducible historical evaluation covering inactive/delisted securities, identifiers/symbol history, corporate actions, raw/adjusted semantics, corrections, licensing, and deterministic ingestion.

## Next implementation slices

1. Build and run the small provider-evaluation harness/dataset once provider credentials are available.
2. Normalize and promote canonical Parquet datasets with DuckDB metadata.
3. Implement point-in-time universe history and eligibility.
4. Add completeness, cross-sectional, corporate-action, and cross-provider quality checks.
5. Prove deterministic historical backfill and incremental-update behavior.

No downstream feature or pattern work should begin until the complete data-foundation acceptance criteria pass.
