# Research Brain Conditioning v0.1

Research Brain Conditioning turns preserved experiment history into an **evidence-quality map**. It is the layer between a descriptive brain review and any future system that proposes follow-up experiments.

Conditioning is deliberately not an optimizer. It does not create a single brain score, rank configurations, select a historical winner, validate a strategy, or promote research. It asks a narrower question: **what kinds of evidence are actually present in this brain, what is still missing, and which missing evidence should be challenged next?**

## Why there is no composite score

The Trade Scout specifications require sample size, uncertainty, comparator effects, parameter stability, multiple testing, and out-of-sample evidence to remain visible rather than being hidden inside a convenient headline number. A large raw expectancy must not compensate for a missing comparator or absent unseen-data test.

Conditioning therefore reports independent dimensions. No weighted average is calculated.

## Conditioning dimensions

Version 0.1 inspects eight dimensions:

1. **Evidence integrity** — whether attached experiment manifests and artifacts remain checksum-verifiable and readable.
2. **Sample support** — whether recognized event/sample counts are present, and whether support varies across result cells. SCOUT does not invent a universal strong/moderate/weak N threshold.
3. **Comparison evidence** — whether attached result artifacts contain an explicit comparator, baseline, benchmark-relative, or excess-return result.
4. **Uncertainty** — whether result artifacts contain confidence/bootstrap intervals, standard errors, p-values, adjusted p-values, or another explicit uncertainty result.
5. **Parameter neighborhood** — for readable one-variable sweeps, the highest historical cell and its immediate numeric neighbors. This maps the local surface but does not call it statistically stable.
6. **Time stability** — whether explicit walk-forward, fold, year-by-year, or other time-sliced result evidence exists.
7. **Out-of-sample evidence** — whether an explicit unseen/holdout/validation result exists. A configuration declaring a validation plan is not counted as a completed validation result.
8. **Search burden** — the number of readable tested sweep cells and whether explicit multiplicity/search-adjustment evidence is present.

Each dimension is labeled as `AVAILABLE`, `PARTIAL`, `MISSING`, `CHECK_NEEDED`, or `NOT_APPLICABLE`. The browser translates those states into plain language such as **Evidence found**, **Needs caution**, and **Not found / not tested**.

## Evidence detection boundary

Conditioning reads **stage output artifacts**, not merely configuration declarations. A configuration saying `out_of_sample_status=NOT_RUN` or a validation period existing in config does not become evidence that validation happened.

The first implementation recognizes a conservative set of result-field names for comparator, uncertainty, out-of-sample, time-stability, multiplicity, and sample-count evidence. Unknown future artifact schemas remain missing until explicitly supported rather than being guessed from unrelated fields.

## Sample-size boundary

Version 0.1 intentionally does not define a universal minimum N. Raw event count is not the same as effective independent sample size, and different research designs have different dependence structures.

When multiple recognized counts exist, conditioning reports the observed range and warns that support is uneven. Any future effective-sample rule belongs in the statistical/validation layer and must be versioned there rather than hidden in the UI.

## Parameter-stability boundary

For a one-variable sweep with at least three numeric points, conditioning shows the historical peak and its immediate neighbors. This makes isolated or uneven surfaces easier to inspect, but the conditioning layer does not use a hidden percentage rule to declare a region stable.

Formal parameter stability still requires the appropriate comparator, uncertainty, sample protection, and validation design.

## Prioritized next evidence step

Conditioning proposes one next evidence priority using a transparent sequence:

1. repair unreadable evidence;
2. add evidence if the brain is empty;
3. establish comparator evidence;
4. establish uncertainty;
5. map the parameter neighborhood when a sweep exists;
6. account for searched parameter families/multiplicity;
7. perform frozen out-of-sample testing;
8. examine time stability/walk-forward behavior.

This ordering follows the project principle that exploratory effects should be challenged before more tuning is added. The recommendation is a research-process suggestion, not an automatically launched experiment.

## Current UI

The Research Brains page now contains a **Brain conditioning — evidence quality map** beneath the descriptive review. It shows all dimensions separately, the supporting artifact paths when present, and one plain-English next priority.

The existing review checkpoint format remains unchanged in v0.1. Review checkpoints preserve the descriptive review and exact membership state; conditioning is currently derived live and deterministically from the same immutable experiment evidence. Persisting conditioning snapshots can be added later without silently reinterpreting existing checkpoints.

## Explicit exclusions

Conditioning v0.1 does not:

- calculate statistical significance itself;
- infer effective sample size from raw N;
- select a best parameter;
- search new parameter values;
- run a comparator or bootstrap procedure;
- run out-of-sample or walk-forward research;
- merge brains;
- launch background experiments;
- generate production eligibility;
- produce a trading recommendation.

Those capabilities remain governed by the existing experiment, statistics, validation, and future research-orchestration layers.
