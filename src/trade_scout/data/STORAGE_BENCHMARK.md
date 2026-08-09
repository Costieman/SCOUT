# Canonical storage benchmark harness

The Data Architecture acceptance criteria require Parquet/DuckDB to be benchmarked on a representative multi-year US-equity sample. `benchmark_canonical_storage` provides the reproducible measurement path for that test; the small automated fixture proves only that the harness works and does **not** satisfy the representative-data acceptance criterion.

For an explicitly supplied sample, the harness records record count, unique instrument count, date coverage, Parquet and DuckDB metadata sizes, canonical promotion time, full-load time, and a filtered DuckDB query time/count. It deliberately reports measurements without inventing pass/fail performance thresholds before the real workload is available.

A benchmark run uses a fresh dataset version and the normal `CanonicalDailyBarStore` promotion path. Therefore the same quality, provenance, immutability, Parquet integrity, and dataset-version controls exercised in research storage are exercised by the benchmark. The final Phase 1 benchmark must use a documented real historical sample drawn from the accepted market-data provider; synthetic CI fixtures cannot substitute for that evidence.

## Registered-dataset replay

`benchmark_registered_dataset` allows an already promoted canonical dataset to be used as benchmark input without downloading the provider history again. The source dataset is first loaded through `CanonicalDailyBarStore`, which verifies its registered Parquet checksum. Its immutable provenance fields are then copied into a fresh promotion request and the exact canonical rows are replayed into a separate benchmark root.

The source root and benchmark root must be distinct. The benchmark never rewrites the source dataset, and a pre-existing target version in the benchmark root is rejected. Replaying the same real canonical sample therefore measures the actual storage path while preserving the original research dataset and avoiding an unnecessary additional provider request.

The command-line runner is:

```text
uv run python scripts/run_storage_benchmark.py \
  --source-root <canonical-runtime-root> \
  --dataset-version <dataset-version> \
  --benchmark-root <fresh-benchmark-root> \
  --query-start YYYY-MM-DD \
  --query-end YYYY-MM-DD
```

It writes JSON and Markdown reports under `<benchmark-root>/report/`. The report deliberately sets representative-sample acceptance to false: whether the source is broad and long enough to satisfy the Phase 1 criterion remains an explicit scientific/engineering review decision rather than an inference from successful execution.
