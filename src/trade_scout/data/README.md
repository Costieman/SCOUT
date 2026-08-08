# Data module

## Purpose

The data module owns provider isolation, canonical market-data contracts, provenance, validation, and the serving boundary consumed by later research modules.

## Explicit non-responsibilities

This module does not calculate technical features, detect patterns/events, evaluate outcomes or stops, rank candidates, issue alerts, or silently repair suspicious market data.

## Completed Phase 1 slice

The first implementation slice establishes:

- permanent internal `InstrumentId` and canonical instrument/symbol-history contracts;
- canonical raw and split-adjusted daily-bar representation;
- explicit `PASS`, `WARN`, `QUARANTINE`, and `REJECT` quality states;
- a vendor-neutral `ProviderAdapter` protocol and capability declaration;
- provider-neutral staging records for instruments, symbols, bars, and corporate actions;
- deterministic structural/market-logic checks for daily bars;
- a stable `ResearchBar` serving contract that never silently changes price representation.

## Provider evaluation direction

The Phase 1 public-documentation screen is recorded in [`docs/research/data-provider-evaluation-v0.1.md`](../../../docs/research/data-provider-evaluation-v0.1.md). Massive is the first primary-provider evaluation candidate, Tiingo is the first secondary-validation candidate, and EODHD is retained as a fallback/tertiary candidate.

This ordering is not provider acceptance. The primary source must still pass a small reproducible historical evaluation covering inactive/delisted securities, identifiers/symbol history, corporate actions, raw/adjusted semantics, corrections, licensing, and deterministic ingestion.

## Next implementation slices

1. Build and run the small provider-evaluation harness/dataset once provider credentials are available.
2. Implement identifier resolution and the instrument master.
3. Persist immutable raw batches and provenance/checksums.
4. Normalize and promote canonical Parquet datasets with DuckDB metadata.
5. Implement point-in-time universe history and eligibility.
6. Add completeness, cross-sectional, corporate-action, and cross-provider quality checks.
7. Prove deterministic historical backfill and incremental-update behavior.

No downstream feature or pattern work should begin until the complete data-foundation acceptance criteria pass.
