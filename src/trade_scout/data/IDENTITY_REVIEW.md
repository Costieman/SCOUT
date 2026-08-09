# Reviewed reference identity links

Current-reference reconciliation deliberately stops at candidate generation. A candidate can only enter the canonical instrument master through a separate, auditable review decision.

## Promotion requirements

- The market-side identity must already resolve exactly through a provider identifier stored on one canonical instrument.
- The reference candidate must have exact current symbol and exchange agreement and exactly one reference row.
- The review must cite non-empty external evidence references, identify the reviewer/process, include a timezone-aware decision timestamp, and state a rationale.
- The review must name exactly the market and reference identities present in the candidate.
- A rejected review cannot modify the instrument master.
- A symbol-only candidate cannot be promoted even if manually marked approved; it remains investigation evidence.

An approved review adds the reference provider association to the existing canonical `InstrumentRecord` through `link_provider_identity`. It does not derive a new permanent identifier from SEC CIK, ticker, company name, or exchange, and it does not infer historical symbol continuity.

The updated instrument collection is returned immutably. Persisting it requires promotion as a new versioned instrument-master snapshot through `InstrumentMasterStore`; an existing snapshot is never edited in place.
