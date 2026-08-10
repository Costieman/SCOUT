# Alpha Vantage + Stooq adjudication gate v0.1

## Purpose

The A+B evidence layer measures agreement, disagreement, and one-sided coverage. It does not itself decide that a missing provider observation should be filled or that one conflicting value is correct.

This gate sits between evidence and canonical promotion. Its purpose is to make every source-selection decision explicit and auditable.

## Default decisions

- `BOTH_AGREE` -> `CORROBORATED`: Alpha Vantage is selected as the existing primary observation only because Stooq independently corroborates the raw OHLCV within configured tolerance.
- `BOTH_DISAGREE` -> `DISCREPANCY_REVIEW_REQUIRED`: no provider is selected.
- `A_ONLY` or `B_ONLY` -> `GAP_REVIEW_REQUIRED`: no provider is selected.

No majority vote, averaging, interpolation, or silent failover is permitted.

## Reviewed decisions

A review-required record may become:

- `PRIMARY_ACCEPTED` when the Alpha Vantage observation survives explicit identity/session/quality review;
- `SECONDARY_ACCEPTED` when the Stooq observation survives explicit identity/session/quality review;
- `REJECTED` when the session cannot be defended from available evidence.

Every reviewed transition requires a non-empty audit note. Final decisions cannot be silently rewritten; a later correction should create a new evidence/revision record rather than mutate history.

## Canonical-storage boundary

This module deliberately stops before canonical storage. The current canonical store requires one `primary_provider_id` for every bar in a dataset version. Allowing a Stooq-selected gap record into the same canonical dataset would therefore change manifest/provenance semantics.

That is an architecture decision, not a convenience patch. Until a reviewed multi-source canonical provenance model is defined, adjudication can identify a defensible selected observation but cannot bypass the current canonical promotion contract.

## Next gate

Before enabling reviewed B-only fills, Trade Scout must define how a canonical dataset records row-level source provenance while preserving a single immutable dataset identity. The design must remain compatible with the existing research contract and must not obscure which provider supplied each accepted observation.
