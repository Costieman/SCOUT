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
