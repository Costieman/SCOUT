# ADR-0004: Provider-adapter boundary

- **Status:** Accepted
- **Date:** 2026-08-08

## Context
Market-data vendors differ in authentication, field names, identifiers, pagination, corrections, and licensing. Vendor behavior must not redefine downstream scientific meaning.

## Decision
Terminate provider-specific behavior at isolated adapters. Downstream modules consume canonical Trade Scout contracts only. Primary-provider data becomes canonical only through the data-quality and promotion process; secondary providers validate rather than being indiscriminately blended.

## Alternatives considered
Direct provider SDK use inside research modules and automatic multi-feed blending were rejected because they create coupling and ambiguous provenance.

## Consequences
Provider SDKs may be added only behind adapter boundaries during the data-foundation milestone. No provider is selected or integrated in Phase 0B.
