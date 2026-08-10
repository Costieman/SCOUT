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

Row provenance is stored as deterministic JSONL under `metadata/composite_row_provenance/<dataset_version>.jsonl`. The store computes a SHA-256 checksum, verifies it on load, permits idempotent re-registration of identical content, and rejects reuse of a dataset version with different provenance.

## Canonical storage compatibility

The existing `CanonicalDailyBarStore` requires one `primary_provider_id` per dataset version. Composite rows therefore carry `provider_id=trade_scout_composite`; the external source is intentionally retained in the row-provenance sidecar rather than overloading `DailyBar.provider_id` with mixed external providers.

This preserves the current immutable Parquet/DuckDB storage contract while making the A+B source selection reconstructible. The next integration step is a composite promotion service that commits the canonical dataset and its provenance manifest as one controlled operation and refuses to expose a composite dataset if either half is missing or inconsistent.
