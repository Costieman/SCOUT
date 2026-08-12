# Experiment Runner

The experiment package is the orchestration and reproducibility boundary for Trade Scout research.
It turns a fully resolved `ExperimentDefinition` into an auditable run without implementing analytical
meaning itself.

## Responsibilities

- assign immutable experiment identities;
- persist PENDING, RUNNING, SUCCEEDED, and FAILED lifecycle state;
- pass the same resolved configuration to ordered research-stage adapters;
- persist small machine-readable stage outputs and checksums;
- aggregate warnings without suppressing failure;
- record dataset, universe, code, schema, hypothesis, mode, seed, and lineage metadata;
- reproduce a successful experiment from its stored definition;
- materialize explicit Cartesian parameter grids before sweep execution;
- expose the accepted first consolidation-breakout Experiment A-J sequence as planning metadata;
- index verified manifests in a queryable DuckDB registry without making the registry authoritative;
- materialize immutable batch plans before execution and retain failed/null child runs.

## Non-responsibilities

The runner does **not** calculate market features, detect patterns/events, calculate forward outcomes,
simulate stops, estimate statistics, choose winning parameter cells, promote strategies, scan current
markets, or deliver alerts. Those responsibilities remain in their domain modules.

## Version 1 persistence and registry

`FileManifestStore` writes one directory per experiment containing `manifest.json` and small JSON stage
artifacts. Manifests are canonicalized and SHA-256 verified on read. Large analytical tables should be
persisted by their owning module using the project data/artifact policy and referenced from stage output
metadata rather than embedded in the manifest.

`DuckDBExperimentRegistry` provides a query index for status, research mode, hypothesis family, dataset
version, and parent/reproduction lineage. `IndexedManifestStore` indexes the checksum-verified persisted
manifest, preserving the manifest as the source of reproducibility truth.

## First research-program plan

`FIRST_RESEARCH_PROGRAM` encodes the controlled A-J sequence from the Version 0.1 consolidation-
breakout research specification. `FirstProgramGrid` records the initially declared trend IDs, duration
values, breakout IDs, outcome horizons, and baseline stop grids. These objects are planning contracts,
not evidence and not permission to skip the data-foundation gate or validation requirements.

The sequence is deliberately dependency-ordered: trend baseline -> duration -> tightness -> breakout ->
volume -> market regime -> stock volatility/age -> simple stops -> frozen combined validation -> walk-
forward/final holdout. Validation rejects reordered or incomplete plans instead of silently accepting an
ad hoc combinatorial search.

## Governed batch planning

`plan_experiment_batch` resolves the complete requested search space before any child run starts and
assigns a deterministic plan checksum/ID. Exploratory research may contain explicit multi-value parameter
grids. Confirmatory and production-monitoring modes reject multi-value search dimensions because those
modes require frozen analytical definitions.

`ExperimentBatchExecutor` then executes the pre-materialized plan through the standard
`ExperimentRunner`. `CONTINUE` mode records failures and attempts the remaining declared children;
`FAIL_FAST` stops after the first failure. Neither behavior removes failed experiments from the research
record, and neither selects a preferred parameter cell.

## Integrity rules

The runner snapshots the supplied resolved configuration and checks after every stage that the stage did
not mutate analytical configuration. Failed stages are recorded durably before an exception is surfaced.
Reproduction creates a new experiment identity and records `reproduction_of`; it never overwrites the
original experiment. Batch-plan identity is derived from the parent definition, declared grid, and all
materialized child-configuration checksums, so a changed search space cannot silently retain the same
plan identity.
