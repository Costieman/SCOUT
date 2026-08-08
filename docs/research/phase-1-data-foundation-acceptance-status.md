# Trade Scout — Phase 1 Data Foundation Acceptance Status

**Date:** 2026-08-08  
**Status:** **NOT YET ACCEPTED**  
**Phase 2 feature work:** **BLOCKED**

## 1. Decision rule

Phase 1 is complete only when Trade Scout can reproduce a defensible historical US-equity dataset from approved provider evidence, preserve immutable raw inputs, resolve permanent identity and point-in-time membership, validate and version canonical data, and serve the same research contract later modules will consume.

Passing unit/integration tests is necessary but not sufficient. Provider entitlement, licensing, real historical edge cases, cross-provider evidence, correction behavior, and representative storage performance must also pass.

## 2. Acceptance matrix

| Acceptance area | Current status | Evidence / remaining work |
|---|---|---|
| Provider-neutral adapter boundary | **PASS — implementation** | Common provider contracts are established; Massive primary-candidate and Tiingo secondary-candidate adapters remain isolated from canonical/research modules. |
| Immutable raw-response preservation | **PASS — implementation and live path** | Massive live evaluation captured exact response bytes before decoding and emitted only sanitized report metadata. Persistent production retention still depends on licensing. |
| Permanent `instrument_id` and provider identity | **PASS — implementation** | Ticker-independent identity resolution, conflict detection, and immutable instrument-master snapshot storage are implemented and tested. |
| Dated symbol history | **PASS — implementation; PARTIAL live evidence** | Interval/conflict rules and immutable symbol-history storage pass tests. The live XYZ control retrieved two dated records. Older symbol-history depth still requires the deeper historical acceptance sample. |
| Canonical daily-bar normalization | **PASS — implementation; PASS on successful live cases** | Exact provider identity, raw/split-adjusted representation, explicit adjustment metadata, and quality propagation are tested. Successful live AAPL/CTAS/XYZ cases normalized with `PASS` and zero normalization/quality issues. |
| Volume representation | **PASS — corrected from live evidence** | First live Massive execution exposed fractional aggregate volume. Provider, canonical, Parquet, research-serving, and reconciliation contracts now preserve numeric volume without integer coercion; regression tests cover provider mapping and Parquet round trip. |
| Canonical daily-bar Parquet + DuckDB | **PASS — implementation** | Immutable versioned promotion, provenance, quality summaries, logical/physical checksums, tamper detection, and idempotency are implemented and tested. |
| Canonical corporate actions | **PASS — implementation** | Provider events resolve only through permanent identity; unresolved events remain explicit; immutable versioned corporate-action Parquet/DuckDB storage and integrity checks are implemented and tested. |
| Structural / contextual data quality | **PASS — implementation** | OHLC logic, duplicates, missing expected observations, cross-sectional counts, unexplained price jumps, and PASS/WARN/QUARANTINE/REJECT gates are tested; no silent repair is introduced. |
| Point-in-time universe | **PASS — implementation; live population not yet accepted** | Temporal, delisting, security-type, price, liquidity, history, and quality gates are implemented and tested without current-universe hindsight. A representative real historical universe still depends on accepted provider depth. |
| Historical backfill orchestration | **PASS — implementation** | Deterministic bounded batches, immutable staging, atomic checkpoints, conflict detection, and resume-after-failure are implemented and tested. Full real historical execution remains blocked by provider acceptance/depth. |
| Incremental correction-lookback revisions | **PASS — implementation** | Parent-to-target immutable revision planning preserves prior history, constrains corrections to an explicit window, and does not create a new dataset version for identical incoming data. |
| Cross-time provider correction detection | **READY — evidence gate open** | Correction snapshots and comparison states are implemented. A second retrieval at a sufficiently later time is required before correction behavior is characterized. |
| Cross-provider reconciliation | **READY — live evidence gate open** | Reconciliation engine and Tiingo secondary candidate exist. A credential-backed secondary sample has not yet been run, so independent provider agreement/disagreement is not accepted. |
| Stable research serving contract | **PASS** | Versioned `ResearchDataRequest` serves explicit price representation, PIT eligibility, and allowed quality states; a downstream contract test consumes only `ResearchBar` and no provider-native objects. |
| Representative Parquet/DuckDB benchmark | **OPEN** | Benchmark harness exists, but the tiny CI fixture is not acceptance evidence. Run on the accepted representative multi-year US-equity sample. |
| Massive historical-depth sample | **OPEN / current credential insufficient** | Earlier 2020/2022 target windows returned HTTP 403 under the current entitlement. The required long-horizon split/dividend/delisted/symbol-history/IPO sample therefore has not passed. |
| Massive current/recent live sample | **PARTIAL PASS** | In v2, AAPL dividend, CTAS split, and XYZ ticker-history controls passed fully. A recent AAPL control and PARA inactive control terminated on HTTP 504. Those timeouts are operational failures, not evidence that market data are absent. Bounded transient-5xx retries are now merged; the sample needs a clean rerun. |
| Massive licensing / permitted use | **OPEN — blocking** | Written clarification is required for persistent raw/canonical storage, version retention, non-display analytics, derived data, backtesting, and private strategy/scanner research. A deeper data entitlement alone does not close this gate. |

## 3. Live Massive evidence to date

The credential-backed evaluation has proved that the secret path works without exposing the key and that the concrete adapter can pass the provider-neutral canonical path on real data.

The most recent completed v2 sample produced these case-level results:

- **AAPL cash-dividend window:** automated gate passed; four daily bars, one required corporate action, repeatable retrieval, and canonical normalization `PASS`.
- **CTAS split window:** automated gate passed; four daily bars, one required split, repeatable retrieval, and canonical normalization `PASS`.
- **XYZ ticker-history control:** automated gate passed; four daily bars, repeatable retrieval, canonical normalization `PASS`, and two dated symbol-history records.
- **Recent AAPL control:** terminated on HTTP 504 before a case report could complete.
- **PARA inactive/delisted control:** terminated on HTTP 504 before a case report could complete.

The run preserved **103 raw-response manifests** in ephemeral workflow storage and deliberately did not upload vendor payload bytes. Subsequent transport hardening now retries bounded transient 500/502/503/504 failures in addition to rate-limit responses. A clean rerun is still evidence required; the previous 504 cases are not silently reclassified as passes.

## 4. External gates that now dominate Phase 1

The project is no longer blocked mainly by missing internal architecture. The remaining decisive evidence is external:

1. **Massive licensing:** obtain written confirmation that the intended persistent/non-display research workflow is permitted, or move to another primary provider/license.
2. **Historical entitlement/depth:** run the agreed older historical sample with sufficient access; current credentials have not provided the required 2020/2022 windows.
3. **Correction behavior:** repeat the same bounded request at a later retrieval time and compare immutable raw/logical checksums.
4. **Independent secondary validation:** configure and run the Tiingo candidate (or another accepted secondary) on a stratified overlap sample and record reconciliation states.
5. **Representative benchmark:** run the canonical Parquet/DuckDB benchmark on the accepted multi-year universe.

## 5. Phase gate

**Do not start Feature Engine, SMA/ATR calculations, consolidation detection, breakout events, outcome analysis, scanner/ranking, or alert logic yet.**

Phase 2 may begin only after the blocking rows above are closed and this document is updated to **ACCEPTED** with the exact provider, license/use assumptions, historical sample evidence, dataset versions, and benchmark evidence recorded.
