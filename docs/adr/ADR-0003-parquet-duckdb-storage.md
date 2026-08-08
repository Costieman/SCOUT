# ADR-0003: Parquet and DuckDB storage direction

- **Status:** Accepted
- **Date:** 2026-08-08

## Context
Historical research requires auditable columnar storage and efficient analytical queries without premature database infrastructure.

## Decision
Use Parquet as the direction for immutable raw/canonical historical datasets and DuckDB for local analytical querying and small metadata stores where appropriate.

## Alternatives considered
A server database, distributed warehouse, and dataframe-only persistence were deferred because Version 1 has not demonstrated a workload requiring that complexity.

## Consequences
The data foundation will benchmark Parquet/DuckDB on a representative sample before scale-driven architecture changes. This ADR does not add either dependency during Phase 0B because no data logic is implemented yet.
