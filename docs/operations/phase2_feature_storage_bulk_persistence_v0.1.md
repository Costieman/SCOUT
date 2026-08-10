# Phase 2 feature storage bulk persistence v0.1

## Purpose

The initial feature snapshot writer used `DuckDBPyConnection.executemany` to insert every
feature observation into a temporary DuckDB table before writing Parquet. On the reviewed
12-instrument slice this meant 276,840 Python-to-DuckDB row insert calls and produced an
operator-observed first-write runtime of roughly 30 minutes on Windows.

This change removes the per-observation SQL insertion path. Feature observations are serialized
to a temporary UTF-8 CSV staging file and imported into the typed DuckDB staging table with one
bulk `COPY` operation. DuckDB then writes the same deterministically sorted ZSTD Parquet output.
The staging file is deleted before the immutable snapshot directory is promoted.

## Semantics that do not change

- Feature definitions and feature-set version remain unchanged.
- Point-in-time calculation semantics remain unchanged.
- Logical content checksum construction remains unchanged.
- Immutable snapshot identity, provenance checks, row-count verification, Parquet checksum
  verification, and reload verification remain unchanged.
- No provider calls are introduced.
- No serving or pattern-engine readiness decision changes.

The optimization is therefore a persistence-path change only. Existing registered snapshots are
never rewritten. Their prior Parquet checksums remain authoritative for those immutable snapshot
identities.

## Regression coverage

The feature storage unit test continues to require exact reload equality and idempotent promotion.
It additionally asserts that the promoted immutable snapshot directory contains only the final
`features.parquet` artifact, proving that temporary bulk-staging material is not retained.

## Operator validation

After merging, validate the optimization using a fresh temporary/synthetic feature snapshot or the
next new immutable canonical dataset version. Do not delete or mutate an already registered private
feature snapshot merely to benchmark the new writer.
