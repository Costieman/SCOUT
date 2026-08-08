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
- Live Massive evaluation workflow using repository-secret credentials, targeted rate-limit-aware evidence collection, and sanitized report artifacts only.
- Evidence-driven fractional-volume support across provider, canonical, Parquet, research-serving, and reconciliation contracts without integer coercion.
