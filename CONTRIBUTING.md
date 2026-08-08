# Contributing to Trade Scout

Trade Scout uses small, reviewable changes and explicit module boundaries.

## Before coding

1. Identify the governing specification or accepted backlog item.
2. Confirm the module responsibility, non-responsibilities, inputs, outputs, dependencies, failure behavior, and required tests.
3. Create a focused branch.

## Local checks

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src/trade_scout
uv run pytest
```

Run `uv run ruff format .` before committing when formatting changes are required.

## Change discipline

- One pull request should represent one coherent change.
- Do not mix broad refactoring with new research behavior.
- Provider-specific logic must remain behind provider adapters.
- Analytical modules must never depend on the dashboard or alerts.
- Reusable research logic belongs in `src/trade_scout/`, not notebooks or scripts.
- No secrets, licensed market datasets, or large generated artifacts may be committed.
- Material architectural changes require an ADR.

## Definition of done

A change is complete only when implementation, typing, tests, documentation, failure behavior, and CI are all appropriate for its scope. Research-impacting changes must additionally be reviewed for point-in-time correctness, leakage, reproducibility, and versioning consequences.
