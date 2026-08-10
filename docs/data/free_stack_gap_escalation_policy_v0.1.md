# Free-stack gap escalation policy v0.1

## Purpose

Trade Scout builds a provenance-preserving research dataset from complementary free sources. Providers are evidence inputs, not winners, and no source is silently promoted to truth.

## Initial stack

1. **Alpha Vantage** — candidate OHLCV and point-in-time listing/delisting evidence.
2. **Stooq** — independent daily OHLCV evidence through the bounded CSV adapter.
3. **SEC EDGAR** — issuer/reference evidence where identity or corporate-history questions require an independent source.

Alpha Vantage and Stooq form the initial price-history comparison pair. SEC EDGAR is not treated as a price feed.

## Gap-first escalation

Do not add another provider merely because it is available. First measure the residual gap after Alpha Vantage and Stooq reconciliation.

For every instrument/session under review, preserve whether each provider:

- supplied an observation;
- did not supply an observation;
- supplied an observation that agrees within the configured tolerance;
- supplied an observation that disagrees and therefore remains unresolved.

A missing observation is not automatically a defect: calendar, listing-state, identity, and corporate-action context must be reviewed before classifying it as a true provider gap.

## Optional Source C

Evaluate a third price source only when the measured residual gap is material enough to justify the additional reconciliation surface.

**Tiingo** is the first candidate for bounded Source-C evaluation because a Trade Scout adapter and cross-provider evidence path already exist. Tiingo must remain validation-only until its current access limits, historical coverage, adjustment semantics, and licensing/redistribution constraints are documented and accepted.

Source C is used to answer a specific unresolved question, not to vote blindly. Three-provider agreement can strengthen evidence; two-versus-one disagreement does not by itself establish truth.

## Specialist escalation

Route gaps according to their type:

- OHLCV/session coverage -> evaluate Tiingo or another bounded price source.
- issuer identity, ticker continuity, filing history -> SEC EDGAR/reference reconciliation.
- split/dividend/corporate-action ambiguity -> use explicit corporate-action evidence and only add another specialist source after a documented gap.
- delisting/universe ambiguity -> point-in-time listing evidence plus identity review; never infer historical membership from the current universe.

## Canonicalization guardrails

- Raw provider payloads remain immutable and provider-specific.
- Provider observations are never averaged to manufacture a canonical bar.
- Missing bars are never interpolated in the canonical raw dataset.
- One provider may fill another provider's absence only after the observation passes identity, date/session, quality, provenance, and representation checks defined by the canonicalization policy.
- Disagreement remains an explicit quality/evidence state until resolved.
- Any later derived/interpolated research layer must be separately labelled, versioned, and reproducible.

## Decision sequence

1. Run bounded Alpha Vantage evidence.
2. Run bounded Stooq evidence.
3. Reconcile the same reviewed instruments and periods.
4. Quantify one-sided coverage and unresolved disagreement by field and case.
5. Classify residual gaps by cause.
6. Escalate only the relevant gap class to Source C or a specialist source.
7. Re-run reconciliation and record whether the additional source actually reduces uncertainty.

The objective is not maximum provider count. The objective is the most complete defensible free research dataset with explicit provenance and measurable uncertainty.
