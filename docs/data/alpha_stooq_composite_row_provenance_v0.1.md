# Alpha Vantage + Stooq composite row provenance v0.1

## Decision

Trade Scout canonical datasets may be assembled from reviewed observations supplied by more than one external provider, but downstream research rows must remain provider-independent. A canonical row therefore uses the dataset-level provider identity `trade_scout_composite`, while an immutable row-provenance sidecar records the external provider observation actually selected for that instrument/session.

This avoids two failure modes:

1. pretending that an Alpha Vantage observation came from Stooq, or vice versa; and
2. leaking provider-specific identifiers into the stable downstream research contract.

## Row provenance

Every reviewed A+B instrument/session receives a provenance record, including rejected observations. The record retains:

- canonical instrument ID and trade date;
- whether the reviewed session entered the canonical dataset;
- selected external provider and provider instrument ID, when one was selected;
- original A+B evidence state;
- final adjudication state and review note;
- providers that directly corroborated the accepted observation.

`BOTH_AGREE` records retain both providers as corroborators even though the deterministic canonical row is materialized from Provider A. A reviewed `B_ONLY` gap fill retains Stooq as the selected source and Stooq alone as direct corroboration. A disagreement that remains unresolved can be rejected and is still preserved in the provenance ledger.

## Normalization boundary

Adjudication does not bypass canonical normalization. The selected provider observation must still resolve through the instrument master and satisfy the existing split-factor, dividend and adjusted-price completeness rules. If normalization cannot produce exactly one canonical row, no canonical row is materialized and the failure remains visible.

## Immutability

Row provenance is stored as deterministic JSONL under `metadata/composite_row_provenance/<dataset_version>.jsonl`, with a persisted checksum manifest beside it. The store verifies SHA-256 and record counts on load, permits idempotent re-registration of identical content, and rejects reuse of a dataset version with different provenance.

## Canonical storage compatibility

The existing `CanonicalDailyBarStore` requires one `primary_provider_id` per dataset version. Composite rows therefore carry `provider_id=trade_scout_composite`; the external source is intentionally retained in the row-provenance sidecar rather than overloading `DailyBar.provider_id` with mixed external providers.

## Controlled promotion

`CompositeDatasetStore` is the fail-closed boundary for publishing an A+B canonical dataset. It requires every accepted canonical row to have exactly one included provenance record with the same instrument/date key and a non-null selected source provider and provider instrument ID. Unresolved normalization issues block promotion.

Provenance is registered before canonical Parquet. This ordering is deliberate: if canonical promotion fails, the remaining provenance sidecar is not research-visible and an identical retry is idempotent. The reverse ordering could expose a canonical composite dataset without its source-row provenance. Loading through the composite store refuses any dataset where either canonical state or provenance is missing or where their row keys disagree.

This preserves the existing immutable Parquet/DuckDB contract while making every accepted A+B observation reconstructible from its reviewed source evidence.
