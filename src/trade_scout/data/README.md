# Data module

## Purpose

The data module owns provider isolation, canonical market-data contracts, provenance, validation, and the serving boundary consumed by later research modules.

## Explicit non-responsibilities

This module does not calculate technical features, detect patterns/events, evaluate outcomes or stops, rank candidates, issue alerts, or silently repair suspicious market data.

## Current Phase 1 slice

The first implementation slice establishes:

- permanent internal `InstrumentId` and canonical instrument/symbol-history contracts;
- canonical raw and split-adjusted daily-bar representation;
- explicit `PASS`, `WARN`, `QUARANTINE`, and `REJECT` quality states;
- a vendor-neutral `ProviderAdapter` protocol and capability declaration;
- provider-neutral staging records for instruments, symbols, bars, and corporate actions;
- deterministic structural/market-logic checks for daily bars;
- a stable `ResearchBar` serving contract that never silently changes price representation.

## Next implementation slices

1. Evaluate the primary and secondary provider candidates on a small historical sample.
2. Implement identifier resolution and the instrument master.
3. Persist immutable raw batches and provenance/checksums.
4. Normalize and promote canonical Parquet datasets with DuckDB metadata.
5. Implement point-in-time universe history and eligibility.
6. Add completeness, cross-sectional, corporate-action, and cross-provider quality checks.
7. Prove deterministic historical backfill and incremental-update behavior.

No downstream feature or pattern work should begin until the complete data-foundation acceptance criteria pass.
