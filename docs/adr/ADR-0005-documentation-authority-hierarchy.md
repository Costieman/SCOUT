# ADR-0005: Documentation authority hierarchy

- **Status:** Accepted
- **Date:** 2026-08-08

## Context
Trade Scout has a master design plus specialist specifications. Without an authority rule, duplicated wording can diverge and implementation decisions can become buried in chat history.

## Decision
Use the hierarchy defined in Document 0: Document 0 is the entry point; the Scope-Control Charter and Phase 0 govern cross-cutting constraints; accepted specialist specifications govern detailed domain behavior; research-program specifications govern individual empirical protocols; ADRs record material technical decisions; code/tests/configuration implement these authorities. More specific accepted specifications govern detailed implementation when wording conflicts, and the inconsistency must then be resolved explicitly.

## Alternatives considered
Treating Document 0 as a complete replacement for specialist specifications, or treating code as the final authority, were rejected.

## Consequences
Repository documentation is indexed and numbered. Missing authoritative documents remain explicit gaps rather than being reconstructed from memory or chat.
