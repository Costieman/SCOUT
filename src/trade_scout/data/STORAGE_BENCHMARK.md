# Canonical storage benchmark harness

The Data Architecture acceptance criteria require Parquet/DuckDB to be benchmarked on a representative multi-year US-equity sample. `benchmark_canonical_storage` provides the reproducible measurement path for that test; the small automated fixture proves only that the harness works and does **not** satisfy the representative-data acceptance criterion.

For an explicitly supplied sample, the harness records record count, unique instrument count, date coverage, Parquet and DuckDB metadata sizes, canonical promotion time, full-load time, and a filtered DuckDB query time/count. It deliberately reports measurements without inventing pass/fail performance thresholds before the real workload is available.

A benchmark run uses a fresh dataset version and the normal `CanonicalDailyBarStore` promotion path. Therefore the same quality, provenance, immutability, Parquet integrity, and dataset-version controls exercised in research storage are exercised by the benchmark. The final Phase 1 benchmark must use a documented real historical sample drawn from the accepted market-data provider; synthetic CI fixtures cannot substitute for that evidence.
