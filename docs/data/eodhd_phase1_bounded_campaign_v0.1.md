# EODHD Phase 1 bounded evidence campaign v0.1

## Purpose

This campaign is a deliberately small provider-evaluation sample. It is intended to reduce uncertainty about whether EODHD can satisfy the Trade Scout Phase 1 primary-provider boundary before any large purchase or historical backfill is treated as canonical.

The campaign does **not** accept EODHD as the canonical provider and does not promote any Phase 1 criterion merely because the run completes.

## Cases

- `AAPL.US`, 2010-01-04 through 2025-12-31: long-lived active security used to test multi-year OHLCV continuity, corporate actions, raw preservation, deterministic normalization, and canonical promotion.
- `META.US`, 2012-05-18 through 2025-12-31: active security with material corporate/name history used to challenge identity continuity and corporate-action handling without assuming ticker permanence.
- `AAIC.US`, 2010-01-04 through 2023-12-31: inactive/delisted case used to test whether terminal historical coverage remains retrievable and promotable rather than disappearing from survivor-only research.

## Evidence expected

A completed run should preserve immutable raw batches and produce case-level evidence for historical OHLCV, provider identity, corporate actions, quality status, canonical dataset identity, and checkpoint/resume state. Failures and empty responses remain evidence and must not be silently substituted.

## Acceptance boundary

The campaign may support later review of reproducible historical backfill, immutable raw preservation, identifier mapping, corporate-action handling, delisting characterization, retry/checkpoint behavior, canonical normalization/quality, and representative-sample readiness. Separate secondary-provider reconciliation, licensing review, deterministic daily-update evidence, point-in-time universe evidence, and the representative Parquet/DuckDB benchmark remain independent requirements.

The selected cases are evaluation fixtures, not a statistically representative US-equity sample. A successful campaign therefore cannot by itself close the Data Foundation acceptance gate.
