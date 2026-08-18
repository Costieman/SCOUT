# Research Brain Reviews

Research Brain Review is the first descriptive synthesis layer built on top of the append-only
research-brain store. Its job is to answer a narrow question: **what does this brain currently
remember, and what can we safely say about that saved evidence without pretending it has been
validated?**

## Inputs

The review consumes only checksum-verified experiment manifests and recorded stage artifacts already
attached to the selected research brain. It does not query market-data providers or rerun research.

Failed experiments remain part of the review. Experiments with broken checksum/status bindings are
reported as unreadable evidence and are excluded from descriptive synthesis until repaired.

## Current descriptive outputs

The first implementation reports:

- how many experiments are remembered, including successes and failures;
- how many are parameter sweeps versus single configurations;
- for saved entry-parameter sweeps, the historically highest and lowest observed expectancy cells;
- complete-event sample support across the sweep;
- explicit warnings when cell sample sizes are uneven;
- brain focus-drift warnings;
- plain-language follow-up questions such as checking neighboring cells and adding an appropriate
  comparator.

The phrase **highest historical cell** is deliberate. The review does not call it a best parameter or
validated optimum.

## Readiness is not a magic experiment count

The review does not use a rule such as "condition after 5 runs" or "condition after 20 runs". It
reports an evidence-coverage state:

- `EMPTY`: no experiment evidence yet;
- `EVIDENCE_CHECK_NEEDED`: one or more attached experiment bindings cannot be verified;
- `FAILURE_HISTORY_ONLY`: useful failed-run history exists, but no successful completed run exists;
- `BASIC_REVIEW_AVAILABLE`: successful saved runs can be summarized but no structured parameter
  surface has been attached;
- `DESCRIPTIVE_REVIEW_AVAILABLE`: at least one structured sweep is available for descriptive review.

These states indicate what kind of **review** is possible. They do not indicate statistical validity
or strategy promotion.

## Scientific boundary

Research Brain Review does not currently calculate or infer:

- confidence or uncertainty intervals;
- matched comparator effects;
- multiplicity-adjusted significance;
- walk-forward or out-of-sample stability;
- production eligibility;
- optimum parameters;
- automatic follow-up experiments;
- cross-brain exchange;
- automated strategy tuning.

If a referenced experiment already contains stronger evidence, later versions may surface that fact,
but the review must never manufacture evidence that is absent from the underlying experiment record.

## Why this comes before automated conditioning

The project charter prefers stability before optimum, preserves null and failed hypotheses, and
requires exploratory work to remain distinct from confirmation. A descriptive review gives future
conditioning machinery a transparent evidence inventory to reason from instead of letting an agent
jump directly from raw historical maxima to new parameter searches.

The next conditioning layer should therefore build on this review and explicitly account for evidence
quality, uncertainty, comparators, multiplicity and unseen-data status before it starts proposing more
aggressive follow-up research.
