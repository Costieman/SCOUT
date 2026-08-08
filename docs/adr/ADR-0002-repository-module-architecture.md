# ADR-0002: Repository and module architecture

- **Status:** Accepted
- **Date:** 2026-08-08

## Context
Trade Scout must prevent research logic, provider logic, application logic, and operations from becoming entangled.

## Decision
Use the module boundaries defined by Document 0 and the Repository Standards specification under `src/trade_scout/`. Dependencies flow downstream: data/common -> features -> patterns -> events -> outcomes/risk -> statistics/validation -> scanner/ranking -> API/application/alerts. Lower analytical layers never import presentation layers.

## Alternatives considered
A flat package and a small number of broad service modules were rejected because they obscure responsibility and permit hidden coupling.

## Consequences
Each module must expose typed contracts and explicit responsibilities before substantive implementation. Empty package boundaries are created now so later work has a stable home without prematurely implementing behavior.
