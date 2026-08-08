# Trade Scout

Trade Scout is a modular quantitative research and market-screening platform. Its governing sequence is **research first, validate second, scan third, alert last**.

## Current milestone

This repository is at **Phase 0B — Repository Bootstrap**. The baseline intentionally contains no market-data integration, feature calculations, pattern detection, backtesting, scanner logic, ranking logic, dashboard logic, or alerts. The next substantive milestone is the historical data foundation.

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

## Repository map

- `src/trade_scout/` — package and domain boundaries
- `configs/` — future defaults, schemas, strategies, and examples
- `docs/` — master design, specifications, ADRs, research, and operations
- `tests/` — unit, integration, synthetic, regression, contract, leakage, and performance scaffolding
- `experiments/` — future schemas/manifests; generated artifacts are excluded from Git
- `scripts/` — narrow operational entry points only
- `notebooks/` — exploratory work only; reusable logic belongs in the package

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

A useful idea that is not required by the active milestone belongs in the backlog. Phase 0B is complete when the package installs, imports, and passes automated quality gates with a clean repository structure.
