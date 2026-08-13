# Statistical Validation Foundation

Trade Scout treats validation as a downstream challenge to a fixed research definition. The validation layer consumes research outputs and records time ordering, comparator identity, sample accounting, uncertainty, robustness results, parameter surfaces, and multiple-testing metadata. It does not redefine patterns, events, outcomes, stops, or ranking rules, and it does not promote strategies automatically.

## Evidence contract

`ComparatorDefinition` identifies the predeclared comparison population. The initial vocabulary covers unconditional observations, trend-matched observations, regime- and sector-matched observations, randomized pseudo-events, and simpler event definitions. Randomized pseudo-event comparators require a recorded seed.

`MetricEstimate` stores a descriptive estimate and optional `ConfidenceInterval`. `EffectEstimate` stores the difference relative to one explicit comparator together with raw/effective sample accounting and, when used, raw and multiplicity-adjusted p-values.

`EvidenceSnapshot` labels evidence as development, validation, walk-forward, final holdout, or robustness evidence. Walk-forward snapshots require a fold identity; robustness snapshots require a challenge identity. `ValidationEvidenceReport` bundles these records without converting them into a scientific promotion decision.

## Evidence completeness

`EvidenceAssignment` explicitly links each evidence snapshot to one frozen validation segment, walk-forward fold, or robustness challenge. `assess_validation_completeness` requires exact target coverage: missing holdout evidence, omitted folds, omitted robustness challenges, role mismatches, unassigned snapshots, or attempts to reuse one snapshot for multiple targets remain visible. `ValidationCompleteness.require_complete()` provides the fail-closed boundary for downstream validation/governance workflows.

Completeness is deliberately not a success criterion. A complete evidence package may still show a null, unstable, or adverse result. The gate proves only that the predeclared validation design was actually represented in the evidence record.

## Multiple testing

`HypothesisFamily` records the complete set of hypotheses before adjustment. `adjust_p_values` refuses partial families, so null or unfavorable tests cannot disappear from multiplicity accounting. The current deterministic methods are exploratory/no adjustment, Bonferroni, and Benjamini-Hochberg false-discovery-rate adjustment.

## Parameter surfaces

`ParameterSurface` requires one cell for every coordinate in the declared Cartesian grid. A surface therefore cannot persist only a winning cell. Each cell retains its sample accounting, estimate, optional uncertainty interval, and warnings. The contract offers exact cell lookup but intentionally provides no `best` or ranking method.

## Review bundle

`assemble_validation_review_bundle` is the final assembly boundary before explicit scientific review. It first requires complete coverage of the frozen validation design, then retains the evidence report, assignments, parameter surfaces, multiplicity family, robustness-plan identity, evidence-role counts, and warnings in one typed package. A declared multiplicity family must be represented exactly rather than supplemented with unrelated families.

`summarize_validation_review` produces a compact inventory for application/reporting layers. The summary reports evidence counts, role counts, parameter-surface identities, multiplicity-family identity, robustness-plan identity, and warning count. It intentionally does not compute a composite score, select a parameter cell, or assign REJECTED/CANDIDATE/VALIDATED status.

## Immutable review persistence

`FileValidationReviewStore` persists a complete `ValidationReviewBundle` as an append-only, deterministic JSON artifact keyed by `report_id`. The bundle payload is serialized in canonical key order and protected by a SHA-256 checksum. The write is atomic and refuses to overwrite an existing report ID, so a review already used in scientific governance cannot be silently revised in place.

Reads fail closed. The store verifies the schema version, filename/envelope identity, payload checksum, and nested typed invariants before returning a review bundle. This means that tampering with estimates, uncertainty intervals, comparator definitions, sample accounting, parameter surfaces, multiplicity metadata, evidence assignments, or completeness state is detected before downstream governance can consume the artifact. Recomputing a checksum over an invalid payload is insufficient because reconstruction reruns the domain-contract validation.

`list_report_ids()` is intentionally only a filesystem inventory operation; callers that need trusted evidence must call `read()` or `checksum()`. Persisted review files remain separate from provider data and experiment outputs, allowing research decisions to cite an independently auditable validation artifact without altering the underlying experiment record.

## Scientific boundary

These objects make evidence auditable; they do not establish that an effect is credible, economically useful, or production eligible. Research status remains an explicit decision recorded through the separate decision-governance layer after the required validation evidence has been reviewed.
