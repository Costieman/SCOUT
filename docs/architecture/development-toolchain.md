# Development Toolchain Baseline

**Accepted:** 2026-08-08

Phase 0B fixes the initial development toolchain so routine quality decisions are not repeatedly reopened during module work.

| Concern | Decision |
|---|---|
| Python | CPython 3.13 (`>=3.13,<3.14`) |
| Project/environment management | `uv` |
| Build backend | Hatchling |
| Formatter | Ruff formatter |
| Linter | Ruff |
| Static type checker | mypy in strict mode |
| Test runner | pytest |
| CI | GitHub Actions |

Dependency versions are resolved through `uv.lock`. Tool configuration lives in `pyproject.toml` where supported. Changes to this baseline should be deliberate and documented when they materially affect reproducibility or contribution workflow.
