# Data module

## Purpose

The data module owns provider isolation, canonical market-data contracts, permanent instrument identity, immutable raw preservation, provenance, validation, cross-provider reconciliation, immutable canonical storage, contextual quality checks, and the serving boundary consumed by later research modules.

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
- provider-reported volume preserved as a numeric value without integer coercion;
- explicit `PASS`, `WARN`, `QUARANTINE`, and `REJECT` quality states;
- a vendor-neutral `ProviderAdapter` protocol and capability declaration;
- provider-neutral staging records for instruments, symbols, bars, and corporate actions;
- deterministic structural/market-logic checks for daily bars;
- cross-provider price/volume comparison with explicit tolerances and no averaging;
- reconciliation states `AGREE`, `PRIMARY_ACCEPTED`, `SECONDARY_CONFIRMED_ERROR`, `UNRESOLVED`, and `NOT_COMPARABLE`;
- reviewed reconciliation decisions that preserve the original provider values and require an audit note;
- point-in-time universe eligibility with explicit temporal and survivorship controls;
- immutable canonical daily-bar promotion to versioned Parquet files;
- DuckDB metadata registry for dataset identity, provenance, quality counts, date coverage, and checksums;
- logical-content and physical-Parquet SHA-256 integrity checks;
- idempotent re-promotion only when both content and provenance are identical;
- explicit rejection of dataset-version reuse, primary-provider mismatch, and quarantined/rejected records;
- completeness checks against caller-supplied point-in-time instrument/session expectations;
- cross-sectional active-instrument count checks against explicit historical count ranges;
- unexplained raw price-jump screening against supplied corporate-action history;
- explicit thresholds and severities for contextual checks rather than hidden quality defaults;
- a stable `ResearchBar` serving contract that never silently changes price representation;
- a reusable real-provider evaluation workflow that consumes a repository secret without exposing it in reports.

## Identity rule

Ticker is display/history metadata, not identity. The first canonical instrument ID is seeded from the primary provider's stable instrument identity and thereafter becomes an opaque Trade Scout key. A second provider must be explicitly linked to that existing key. The system does not merge records merely because ticker, name, or exchange look similar.

This bootstrap rule supports deterministic reconstruction from the same primary-provider identity while preserving the ability to attach additional provider IDs later. Provider replacement therefore requires preserving or explicitly migrating the instrument master; it must not silently regenerate identity from a new ticker list.

## Raw-zone rule

Raw vendor bytes are stored before normalization whenever licensing permits. A raw batch contains an exact payload and a machine-readable manifest recording provider, endpoint/product name, non-secret request parameters, timezone-aware retrieval timestamp, checksum, content length, and optional provider revision. Existing batches are never overwritten. A corrected provider response must receive a new batch identity.

Runtime raw data belong outside Git; tests use temporary directories only.

## Canonical-storage rule

Research-ready daily bars are promoted into `canonical/equities_daily/<dataset_version>/daily_bars.parquet`. A separate `metadata/datasets.duckdb` registry records the immutable dataset identity, canonical provider, source raw batches, transformation/adjustment/universe/quality-definition versions, quality counts, date coverage, logical-content checksum, and physical Parquet checksum.

A dataset version cannot be silently rewritten. Repeating the exact same promotion is idempotent; changing either the data or provenance requires a new dataset version. `QUARANTINE` and `REJECT` records are not eligible for research-ready promotion. Runtime Parquet and DuckDB files remain outside Git.

DuckDB is deliberately the only new storage dependency for this slice because it can both write/read Parquet and maintain the local metadata registry. This preserves the accepted Parquet/DuckDB architecture without introducing a broader dataframe or database stack.

## Contextual quality rule

Coverage and cross-sectional checks do not infer today's universe backward. The caller supplies the historical instrument/session expectations or active-count ranges to be tested. Missing expected observations remain missing and are reported explicitly; the quality layer does not manufacture bars or shorten history windows.

Corporate-action consistency screening compares successive raw closes and flags large moves only when the configured threshold is crossed and no supplied action exists between the two observations. The check is deliberately diagnostic: it does not claim that a recorded action mathematically explains the move, and it never adjusts prices or rewrites source data.

Thresholds and issue severity are explicit policy inputs. This keeps data-quality sensitivity auditable and prevents a convenient default inside a validator from silently changing which batches are considered usable.

## Volume rule

Provider-reported volume is preserved as a floating-point numeric value through staging, canonical storage, research serving, and cross-provider reconciliation. Trade Scout does not round a fractional provider volume to satisfy an integer schema. Exact raw response bytes remain the audit source for the vendor representation.

This policy was tightened after the first real Massive execution returned a non-integral aggregate volume. The correction was made at the data contract rather than by coercing the observation.

## Reconciliation rule

Secondary-provider values are validation evidence, not replacement truth. Trade Scout compares matching instrument/date records using explicit price and volume tolerances. Material differences remain `UNRESOLVED` until a reviewed decision is recorded. The reconciliation layer does not average feeds, silently replace the canonical primary value, or compare records whose identity/date does not match.

## Provider evaluation direction

The Phase 1 public-documentation screen is recorded in [`docs/research/data-provider-evaluation-v0.1.md`](../../../docs/research/data-provider-evaluation-v0.1.md). Massive is the first primary-provider evaluation candidate, Tiingo is the first secondary-validation candidate, and EODHD is retained as a fallback/tertiary candidate.

The first live Massive execution is recorded in [`docs/research/massive-live-evaluation-2026-08-08.md`](../../../docs/research/massive-live-evaluation-2026-08-08.md). The current-data MSFT sample passes the provider-neutral retrieval, repeatability, identity, normalization, and initial quality checks. The required 2020/2022 historical samples return HTTP 403 under the current entitlement, so Massive is **not** accepted as the canonical provider.

Provider acceptance still requires sufficient historical entitlement, licensing/storage confirmation, historical split/dividend/delisted/symbol-change/IPO cases, correction-revision characterization, independent secondary reconciliation, and a representative storage benchmark.

## Next implementation slices

1. Re-run the agreed Massive historical sample only after sufficient historical entitlement is available.
2. Confirm the intended Massive licensing/storage model before persistent vendor data are retained as research assets.
3. Characterize corrections by comparing immutable raw checksums across separated retrieval times.
4. Resolve first-trade/IPO boundary evidence for the point-in-time instrument master.
5. Run the secondary-provider reconciliation sample.
6. Benchmark Parquet/DuckDB on a representative multi-year US-equity dataset.

No downstream feature or pattern work should begin until the complete data-foundation acceptance criteria pass.
