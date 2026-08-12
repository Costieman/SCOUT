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
- materialize explicit Cartesian parameter grids before sweep execution.

## Non-responsibilities

The runner does **not** calculate market features, detect patterns/events, calculate forward outcomes,
simulate stops, estimate statistics, choose winning parameter cells, promote strategies, scan current
markets, or deliver alerts. Those responsibilities remain in their domain modules.

## Version 1 persistence

`FileManifestStore` writes one directory per experiment containing `manifest.json` and small JSON stage
artifacts. Manifests are canonicalized and SHA-256 verified on read. Large analytical tables should be
persisted by their owning module using the project data/artifact policy and referenced from stage output
metadata rather than embedded in the manifest.

## Integrity rules

The runner snapshots the supplied resolved configuration and checks after every stage that the stage did
not mutate analytical configuration. Failed stages are recorded durably before an exception is surfaced.
Reproduction creates a new experiment identity and records `reproduction_of`; it never overwrites the
original experiment.
