# Statistical Validation Foundation

Trade Scout treats validation as a downstream challenge to a fixed research definition. The validation layer consumes research outputs and records time ordering, comparator identity, sample accounting, uncertainty, robustness results, parameter surfaces, and multiple-testing metadata. It does not redefine patterns, events, outcomes, stops, or ranking rules, and it does not promote strategies automatically.

## Evidence contract

`ComparatorDefinition` identifies the predeclared comparison population. The initial vocabulary covers unconditional observations, trend-matched observations, regime- and sector-matched observations, randomized pseudo-events, and simpler event definitions. Randomized pseudo-event comparators require a recorded seed.

`MetricEstimate` stores a descriptive estimate and optional `ConfidenceInterval`. `EffectEstimate` stores the difference relative to one explicit comparator together with raw/effective sample accounting and, when used, raw and multiplicity-adjusted p-values.

`EvidenceSnapshot` labels evidence as development, validation, walk-forward, final holdout, or robustness evidence. Walk-forward snapshots require a fold identity; robustness snapshots require a challenge identity. `ValidationEvidenceReport` bundles these records without converting them into a scientific promotion decision.

## Multiple testing

`HypothesisFamily` records the complete set of hypotheses before adjustment. `adjust_p_values` refuses partial families, so null or unfavorable tests cannot disappear from multiplicity accounting. The current deterministic methods are exploratory/no adjustment, Bonferroni, and Benjamini-Hochberg false-discovery-rate adjustment.

## Parameter surfaces

`ParameterSurface` requires one cell for every coordinate in the declared Cartesian grid. A surface therefore cannot persist only a winning cell. Each cell retains its sample accounting, estimate, optional uncertainty interval, and warnings. The contract offers exact cell lookup but intentionally provides no `best` or ranking method.

## Scientific boundary

These objects make evidence auditable; they do not establish that an effect is credible, economically useful, or production eligible. Research status remains an explicit decision recorded through the separate decision-governance layer after the required validation evidence has been reviewed.
