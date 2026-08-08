# ADR-0001: Python analytical core

- **Status:** Accepted
- **Date:** 2026-08-08

## Context
Trade Scout is primarily a statistical research system requiring strong numerical, data, testing, and scientific-computing support.

## Decision
Use Python as the analytical core. The Phase 0B baseline supports Python 3.13 only (`>=3.13,<3.14`). The package uses a `src/` layout and must install as a normal Python project.

## Alternatives considered
R, Julia, and a polyglot analytical core were left open for isolated future needs but rejected as the primary Version 1 core because they would increase environment and interface complexity before evidence of need.

## Consequences
Analytical interfaces, tests, and package tooling target Python 3.13. A future Python-version expansion is an explicit compatibility decision, not an accidental side effect.
