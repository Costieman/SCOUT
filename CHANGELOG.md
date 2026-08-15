# Changelog

All notable software changes to Trade Scout will be recorded here. Dataset, strategy, configuration-schema, and analytical-definition versions evolve independently.

## [Unreleased]

### Added
- Phase 0B repository scaffold.
- Python packaging and development toolchain.
- Documentation hierarchy and initial ADR set.
- Automated CI quality gates and package smoke test.
- Phase 1 canonical instrument, symbol-history, daily-bar, corporate-action, provenance, and research-serving contracts.
- Provider-neutral adapter protocol, request models, capability declaration, and normalized staging records.
- Initial deterministic daily-bar quality rules with explicit PASS/WARN/QUARANTINE/REJECT behavior.
- Unit and contract tests for the first data-foundation slice.
- Phase 1 provider-evaluation baseline, acceptance matrix, and sample-design gate.
- Permanent instrument-ID derivation, explicit cross-provider identity linking, and point-in-time symbol-history resolution.
- Immutable raw-batch persistence with SHA-256 integrity, provenance manifests, secret-parameter rejection, and idempotency checks.
- Point-in-time universe eligibility with explicit temporal, delisting, security-type, quality, price, liquidity, and trading-history gates.
- Cross-provider daily-bar reconciliation with explicit tolerances, audit states, and no feed blending.
- Versioned canonical daily-bar Parquet storage with DuckDB dataset metadata, provenance, quality summaries, integrity checks, and immutable promotion behavior.
- Contextual completeness, cross-sectional coverage, and unexplained corporate-action price-jump quality checks with explicit policy thresholds.
- Provider-neutral daily-bar normalization with exact identity resolution, explicit adjustment metadata, and per-record quality status propagation.
- Deterministic incremental canonical revision planning with explicit correction windows, append/correction accounting, and no implicit historical deletion.
- Versioned `ResearchDataRequest` serving with point-in-time eligibility, explicit price representation, quality gates, and a provider-independent downstream `ResearchBar` contract test.
- Reproducible canonical-storage benchmark harness reporting Parquet/DuckDB size, promotion, load, and filtered-query measurements without inventing performance thresholds.
- Reusable provider-evaluation harness for capability, inactive/delisted, deterministic retrieval, canonical normalization, corporate-action, and symbol-history sample checks while preserving external licensing/raw-revision acceptance gates.
- Massive candidate Stocks REST adapter with FIGI-based identity, active/inactive reference retrieval, paired raw/split-adjusted daily bars, corporate actions, experimental ticker-event history, same-host pagination checks, and optional immutable raw response capture.
- Deterministic historical daily-bar backfill planning with bounded date/symbol batches, immutable staged provider-neutral batches, atomic checkpoints, and resume-after-failure semantics.
- Immutable versioned instrument-master and symbol-history Parquet snapshots registered in the shared DuckDB metadata catalog with logical/physical checksums and identity/history integrity validation.
- Tiingo EOD secondary-validation candidate adapter with explicit stable identity links, raw OHLCV, split/dividend evidence, header-only token authentication, and deliberate rejection of Tiingo total-return adjusted OHLC as Trade Scout split-adjusted prices.
- Provider-neutral corporate-action normalization with permanent identity resolution plus immutable versioned corporate-action Parquet/DuckDB storage and integrity/provenance checks.
- CI-enforced architecture acceptance checks for module skeleton, dependency direction, governance files, and unique ADR identities.
- Synthetic end-to-end research-to-replay acceptance coverage preserving pattern/event, evidence-package, risk-policy, and dataset provenance.

### Changed
- Provider, canonical, Parquet, research-serving, and reconciliation volume contracts now preserve provider-reported fractional volume instead of requiring integer coercion.
- Risk-policy comparison aggregation now lives in the statistics layer so event-level risk evaluation no longer depends on downstream statistical interpretation.
- Repository status documentation now distinguishes software-foundation completion from real-data research acceptance and production readiness.
