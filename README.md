# Trade Scout

Trade Scout is a modular quantitative research and market-screening platform. Its governing sequence is **research first, validate second, scan third, alert last**.

## Current milestone

The current development stack is completing an **architecture and acceptance sweep of the research-to-replay foundation**.

Implemented foundations now include:

- provider-isolated canonical data, quality, storage, and point-in-time universe contracts;
- registered feature, pattern, and event interfaces with deterministic synthetic/leakage coverage;
- forward outcome-path measurement with explicit truncation and daily-bar ambiguity;
- event-level risk/stop evaluation plus statistics-layer policy comparison;
- reproducible experiment manifests, A-J research-program templates, validation governance, and dependency preflight;
- canonical research-evidence packaging with explicit decision boundaries; and
- historical scanner replay that reuses the shared Pattern/Event implementation and enforces production eligibility.

This is **foundation completion, not a claim that the trading research is complete or production-ready**. Real canonical-data acceptance for the first research program still has to be completed, Experiments A-J still have to be run and interpreted on approved historical data, and no strategy should be treated as production-eligible without explicit validated evidence and governance.

Live `END_OF_DAY` / `INTRADAY` scanning, a validated ranking model, production scanner persistence/scheduling, UI publication, alert delivery, and live operations remain outside the completed foundation.

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

A read-only local application surface also exists for evidence-backed project/data-health workflows:

```bash
uv run python scripts/serve_trade_scout.py --open-browser
```

This serves `http://127.0.0.1:8765/` by default. Presentation surfaces do not own analytical definitions or provider credentials.

## Repository map

- `src/trade_scout/data/` — provider adapters, canonical data, quality, serving contracts
- `src/trade_scout/universe/` — point-in-time eligibility
- `src/trade_scout/features/` — registered point-in-time measurements
- `src/trade_scout/patterns/` — objective persistent pattern state
- `src/trade_scout/events/` — discrete event generation and lifecycle consumption
- `src/trade_scout/outcomes/` — unmanaged post-event path measurement
- `src/trade_scout/risk/` — event-level stop/exit policy evaluation
- `src/trade_scout/statistics/` — aggregation, comparator and policy-comparison analysis
- `src/trade_scout/validation/` — holdout, walk-forward, robustness and evidence packaging
- `src/trade_scout/experiments/` — reproducible experiment orchestration and governance
- `src/trade_scout/scanner/` — fixed-definition historical replay and later production scan contracts
- `src/trade_scout/ranking/` — reserved for independently validated prioritization
- `src/trade_scout/alerts/` — reserved for scanner-state alert decisions/delivery interfaces
- `src/trade_scout/api/`, `src/trade_scout/app/` — application/presentation boundary
- `configs/` — defaults, schemas, strategies, and examples
- `docs/` — master design, specifications index, ADRs, research, architecture, and operations
- `tests/` — unit, integration, synthetic, regression, contract, leakage, architecture, and performance tests
- `experiments/` — schemas/manifests; generated or licensed artifacts are excluded from Git
- `scripts/` — narrow operational entry points only

## Documentation authority

1. [Document 0 — Master System Design & Traceability Map](docs/00-master-system-design/README.md)
2. Project Principles & Scope-Control Charter
3. Phase 0 Architecture, Governance and Build Standards
4. Accepted domain specifications
5. Research-program specifications
6. Architecture Decision Records (ADRs)
7. Code, tests, and configuration implement accepted specifications; they do not silently redefine them.

See [`docs/README.md`](docs/README.md) for the complete documentation index and known source-document gaps.

## Scope-control rule

A useful idea that is not required by the active milestone belongs in the backlog. The next scientific milestone is to prove the data and then execute the governed research program—not to add more signals by assumption.
