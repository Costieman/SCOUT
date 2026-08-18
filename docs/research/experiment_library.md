# Experiment Library

The Experiment Library is the user-facing view of Trade Scout's governed experiment registry.

## Authority boundary

The DuckDB registry is a query index only. Checksum-verified experiment manifests and recorded stage
artifacts remain authoritative. Opening the library synchronizes any verified `*/manifest.json`
records that already exist under the private experiment root into the registry, which lets older
plain-`FileManifestStore` research become discoverable without rewriting its evidence.

The library is presentation and discovery infrastructure. It does not calculate features, signals,
outcomes, risk policies, statistical validation, research decisions, or production eligibility.

## Current capabilities

`/research/experiments` provides:

- search by experiment ID, name, hypothesis, family, dataset, code, and hypothesis family;
- filters for execution status, research mode, strategy family, dataset version, code version, and
  hypothesis family;
- visibility of successful and failed experiments rather than success-only history;
- checksum-verified detail views with the complete resolved configuration and stage artifacts;
- parent / reproduction lineage plus direct children;
- user-selected comparison of two to four experiments;
- configuration differences and result glimpses without a composite score;
- a Strategy Builder re-run action when the current workbench uses the same immutable dataset.

The re-run action deliberately says **current code**. It restores the saved Strategy Builder settings
and creates a new exploratory experiment, but it is not represented as exact historical-code
reproduction. Exact reproduction requires the original analytical environment and remains a
separate operations workflow.

## What is intentionally not implemented here

- automatic experiment ranking or winner selection;
- scientific promotion or rejection decisions;
- automatic brain/research-agent membership;
- exact code-environment reproduction from the browser;
- background scheduling, cancellation, or resume;
- PDF generation;
- deletion of finalized research evidence.

Those concerns remain downstream of the experiment record itself.

## Private storage

The normal research workbench uses:

```text
<workspace>/research/experiments/
  registry.duckdb
  exp_.../manifest.json
  exp_.../artifacts/*.json
```

No registry or manifest is written into the Git repository and the Experiment Library makes no
market-data provider calls.
