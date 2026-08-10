# Trade Scout

Trade Scout is a modular quantitative research and market-screening platform. Its governing sequence is **research first, validate second, scan third, alert last**.

## Current milestone

The repository has completed **Phase 0B — Repository Bootstrap** and is now in **Phase 1 — Data Foundation**. The active implementation is limited to provider isolation, canonical market-data contracts, immutable/provenance-aware ingestion, data quality, storage, and point-in-time universe construction.

No feature calculations, pattern detection, backtesting, scanner logic, ranking logic, dashboard analytical logic, or alerts belong in this milestone. A read-only Data Health presentation shell is permitted only to expose Phase 1 evidence and blocking state; it must not become an analytical implementation.

## Toolchain

- Python 3.13 only (`>=3.13,<3.14`)
- `uv` for environment and dependency management
- Hatchling as the build backend
- Ruff for formatting and linting
- mypy for static type checking
- pytest for automated tests

## Quick start

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src/trade_scout
uv run pytest
```

To view the current evidence-backed Phase 1 interface locally:

```bash
uv run python scripts/serve_trade_scout.py --open-browser
```

This serves `http://127.0.0.1:8765/` by default. The surface is read-only, reloads persisted Data Health evidence, and contains no market-data-provider calls or trade controls. See [`docs/ui/local_console_v0.1.md`](docs/ui/local_console_v0.1.md).

## Repository map

- `src/trade_scout/` — package and domain boundaries
- `configs/` — future defaults, schemas, strategies, and examples
- `docs/` — master design, specifications, ADRs, research, and operations
- `tests/` — unit, integration, synthetic, regression, contract, leakage, and performance tests
- `experiments/` — future schemas/manifests; generated artifacts are excluded from Git
- `scripts/` — narrow operational entry points only
- `notebooks/` — exploratory work only; reusable logic belongs in the package

The active data-module contract and implementation notes are documented in [`src/trade_scout/data/README.md`](src/trade_scout/data/README.md).

## Documentation authority

1. [Document 0 — Master System Design & Traceability Map](docs/00-master-system-design/README.md)
2. Project Principles & Scope-Control Charter
3. Phase 0 Architecture, Governance and Build Standards
4. Accepted domain specifications
5. Research-program specifications
6. Architecture Decision Records (ADRs)
7. Code, tests, and configuration implement accepted specifications; they do not silently redefine them.

See [`docs/README.md`](docs/README.md) for the complete documentation index and current gaps.

## Scope-control rule

A useful idea that is not required by the active milestone belongs in the backlog. Phase 1 is complete only when the historical data foundation satisfies its accepted reproducibility, point-in-time, quality, storage, and serving criteria.
