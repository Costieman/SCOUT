# Canonical Research Evidence Package

## Purpose

The research evidence package is the review and reporting boundary for a completed Trade Scout experiment. It joins immutable experiment provenance with the typed statistical evidence already produced by the validation framework. It does not rerun analysis, calculate missing statistics, choose a best parameter cell, or infer promotion.

This implements the reporting requirements in the Research Methodology and First Research Program specifications: raw and dependence-aware sample information, outcome distributions, win probability with uncertainty, expectancy, MAE/MFE distributions, comparator effects, out-of-sample evidence, walk-forward folds, robustness challenges, multiplicity information where used, and an explicit research-decision state when one has actually been recorded.

## Package contents

`ResearchEvidencePackage` retains:

- experiment ID, name, hypothesis, research mode, hypothesis-family and parent lineage;
- exact dataset, point-in-time universe, code, and configuration-schema versions;
- resolved-configuration checksum, experiment-manifest checksum, and stage-output checksums;
- validation report and validation-plan identities;
- an explicitly selected primary evidence snapshot;
- raw event count, unique instruments, effective sample size, cluster count, and exclusions through `SampleAccounting`;
- the complete primary metric set and comparator effects;
- all validation snapshots, with walk-forward folds, robustness challenges, and final holdout kept separate;
- parameter-surface identities;
- complete registered multiplicity families and adjusted p-values when present;
- robustness-plan identity;
- report notes and warnings; and
- an optional explicit `ResearchDecision`.

The package checksum is deterministic. Any change in experiment provenance, primary evidence, validation snapshots, multiplicity records, or decision evidence produces a different package identity.

## Statistical reporting profile

`canonical_research_reporting_profile()` implements a fail-closed Version 0.1 reporting contract. The explicitly selected primary snapshot must include:

- mean outcome;
- median outcome;
- win probability with an uncertainty interval;
- expectancy;
- at least three named return quantiles;
- at least three named MAE quantiles;
- at least three named MFE quantiles; and
- at least one predeclared comparator effect.

The research specifications require quantile reporting but do not prescribe one universal set of quantile probabilities. For that reason the package does not silently choose percentiles. Evidence producers name the probabilities explicitly, for example `return_quantile_p05` or `mae_quantile_p90`, and the reporting profile verifies that multiple distribution points are present.

Required evidence roles are also explicit inputs to the reporting profile. A confirmatory or final-holdout package can therefore require `VALIDATION`, `WALK_FORWARD`, `ROBUSTNESS`, and `FINAL_HOLDOUT` evidence without forcing those roles onto an exploratory experiment whose frozen design did not contain them.

## Primary evidence is explicit

The package builder requires `primary_evidence_id`. It never chooses the most favorable fold, the latest result, or the final holdout automatically. This is intentional: the reporting layer must not create a hidden selection rule.

Walk-forward folds remain separate records and are not silently pooled. Robustness challenges remain separate records and are not averaged into a single score. Final-holdout evidence remains visibly distinct from development and ordinary validation evidence.

## Decision boundary

A package may contain no research decision. In that case the evidence is still reportable and auditable, but the package has no inferred scientific status.

If a `ResearchDecision` is supplied, it must explicitly cite the packaged experiment. The package preserves the decision state and rationale exactly; it does not derive `CANDIDATE`, `VALIDATED`, or `PRODUCTION-ELIGIBLE` from statistical metrics.

Production eligibility remains governed by the existing decision ledger and production-attestation rules.

## Relationship to existing validation objects

The package builds on, rather than replaces:

- `ExperimentManifest` for immutable experiment provenance;
- `ValidationEvidenceReport` for typed metric/effect snapshots;
- `ValidationReviewBundle` for complete validation-target coverage;
- `SampleAccounting` for raw and dependence-aware sample information;
- `MultiplicitySummary` for registered hypothesis families and adjusted p-values;
- `ParameterSurface` for stability surfaces; and
- `ResearchDecision` for explicit scientific governance.

The builder requires a `SUCCEEDED` experiment manifest with a stored manifest checksum and a complete review bundle for the same experiment.

## Scientific boundary

A complete evidence package is not evidence of an edge by itself. It is evidence that the research result is packaged in a reproducible form suitable for review.

The package does not:

- promote a strategy automatically;
- convert exploratory evidence into confirmatory evidence;
- replace missing metrics with proxies;
- pool walk-forward folds implicitly;
- hide unfavorable robustness results;
- substitute a nearby dataset, universe, comparator, or horizon;
- reinterpret MAE/MFE using a stop policy; or
- claim tradability without the separately required cost, liquidity, and risk evidence.

## Intended downstream use

The package is the canonical source for the Experiment Results Overview, Experiment Library audit view, direct experiment comparison, exported experiment summary reports, and later strategy-evidence profiles. UI and export layers may format or visualize the package, but they must not alter its analytical contents or checksum identity.
