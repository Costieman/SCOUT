# Research-to-Replay Architecture & Acceptance Sweep v1

**Date:** 2026-08-15  
**Scope:** software foundation from canonical research inputs through governed historical scanner replay  
**Status:** foundation accepted with explicit deferred scientific and production gates

## 1. Purpose

This sweep cross-checks the implemented research-to-replay foundation against Document 0, the Phase 0 architecture, Repository Standards, and the specialist research/pattern/risk/scanner contracts. Specialist specifications remain authoritative for detailed behavior; this report records implementation status and gaps rather than redefining those specifications.

The governing principle remains: **research first, validate second, scan third, alert last**.

## 2. Concrete defects corrected in this sweep

### 2.1 Risk/statistics dependency inversion

The risk-policy comparison harness previously lived under `trade_scout.risk` while importing `trade_scout.statistics.stop_research`. That made a lower risk layer depend on downstream statistical interpretation.

Correction:

- event-level stop/exit evaluation remains in `trade_scout.risk`;
- cross-policy aggregation and comparison moved to `trade_scout.statistics.risk_policy_comparison`;
- the public comparison entry point is now exported from `trade_scout.statistics`;
- the comparison harness definition version advances to `risk-policy-comparison-harness-v0.2`.

The analytical stop semantics are unchanged; this is an architecture-boundary correction.

### 2.2 Duplicate ADR identifier

Two unrelated decisions used `ADR-0004`. The free-data-first provider strategy is now `ADR-0007`; the provider-adapter boundary remains `ADR-0004`. CI now requires unique ADR identifiers and matching filename/header IDs.

### 2.3 Stale project-status documentation

The root README and Document 0 repository stub still described Phase 0B/Phase 1 as the current implementation milestone. They now distinguish the historical Document 0 roadmap baseline from current repository status and explicitly state that foundation completion is not equivalent to completed research or production readiness.

### 2.4 Dependency rules were review-only

Repository dependency direction was documented but not mechanically guarded. The architecture test suite now AST-checks protected modules for forbidden downstream imports and verifies the canonical module skeleton, governance files, and ADR identity rules.

## 3. Acceptance matrix

### Foundation accepted

| Area | Acceptance state | Evidence in the implementation |
|---|---|---|
| Repository/tooling | PASS | Canonical module skeleton, centralized Python/Ruff/mypy/pytest tooling, CI hygiene and quality gates. |
| Data contracts | PASS — software foundation | Provider-neutral canonical contracts, explicit quality states, immutable/versioned serving boundaries and point-in-time universe machinery. |
| Synthetic market laboratory | PASS | Deterministic known-behavior fixtures for trends, breakouts, missing bars, splits, volatility shocks, gaps, stop-outs and daily-bar ambiguity. |
| Pattern/Event | PASS — synthetic/contract | Persistent lifecycle, one-time event consumption, explicit invalidation, corporate-action handling, no-outcome leakage, batch/incremental equivalence. |
| Outcome paths | PASS — synthetic/contract | Next-session-open convention, complete/truncated states, MAE/MFE, gap metrics and bounded daily-bar drawdown ambiguity. |
| Risk | PASS — exploratory infrastructure | Same event population across policies, gap-through fills, cost hooks, structural/ATR interfaces and explicit same-bar ambiguity. |
| Experiment governance | PASS | Immutable definitions/manifests, exploratory vs confirmatory modes, lineage, A-J templates and fail-closed dependency preflight. |
| Validation/evidence | PASS — software foundation | Time-ordered evidence roles, multiplicity/robustness metadata, canonical research evidence package and explicit decision boundary. |
| Scanner replay | PASS — replay foundation | Historical point-in-time truncation, production-eligibility gate, research-preview separation, shared Pattern/Event implementation, deterministic provenance. |
| Research -> replay traceability | PASS — synthetic acceptance | End-to-end acceptance test preserves event/pattern identity, dataset identity, research-evidence package checksum and selected risk-policy identity into replay output. |
| Dependency direction | PASS — guarded | CI architecture test blocks known upward imports in protected modules. |

## 4. Gates that remain scientifically open

The following are **not** satisfied by synthetic/contract acceptance and must not be described as completed research:

- final real-data acceptance for the canonical dataset used by the first research program;
- approved point-in-time historical universe coverage sufficient for the intended claims;
- execution of Experiments A-J on that accepted immutable dataset;
- empirical interpretation of parameter surfaces, comparator effects, uncertainty, multiplicity and robustness;
- evidence-based selection or rejection of a candidate strategy;
- independent validation of any promoted risk policy;
- an explicit VALIDATED and then, where justified, PRODUCTION-ELIGIBLE governance decision.

Until those gates are crossed, synthetic production-eligibility objects are test fixtures only and have no scientific standing.

## 5. Production capabilities deliberately not accepted

The following remain unimplemented or intentionally blocked:

- live/end-of-day scanner scheduling and persisted scan-run operations;
- finalized production freshness thresholds and ingestion-completion gates;
- validated composite ranking or ranking optimization;
- production scanner UI publication and candidate evidence drill-down tied to real approved strategy versions;
- alert transition engine, duplicate suppression, cooldown and delivery adapters;
- end-to-end historical alert replay;
- production monitoring/strategy-decay state handling;
- full deployment, backup, recovery and operational reproduction workflow.

No architecture acceptance result in this document authorizes these capabilities by implication.

## 6. Documentation gaps

The repository indexes the governing specialist specifications, but their authoritative PDFs remain in the project design set rather than under `docs/specifications/`. The documentation index also explicitly records Document 3 — Research Methodology & Statistical Validation Specification — as a source-document gap rather than reconstructing it.

Therefore this sweep does **not** declare the complete documentation set fully self-contained inside Git. The authority gap should be resolved by adding the authoritative source material or an approved replacement; it must not be filled from memory or chat history.

## 7. Scope conclusion

The software foundation now supports a coherent, CI-guarded chain:

`canonical data -> features -> pattern/event -> outcome/risk -> statistics/validation -> research evidence -> historical replay`

That chain is sufficiently defined for the next scientific stage to depend on it. The appropriate next work is not additional signal engineering. It is:

1. close the real canonical-data acceptance gate for the first research program;
2. freeze the required unresolved research inputs through the dependency planner;
3. execute Experiments A-J in governed order;
4. review the resulting evidence without promoting a strategy automatically;
5. only after explicit validation, consider the production scanner/ranking/alert stages.

**Acceptance statement:** the research-to-replay **software foundation** is accepted subject to CI and the explicit gaps above. Trade Scout is **not yet research-complete and not production-ready**.
