# Reviewed identity promotion gate v0.1

## Purpose

This gate promotes a **reviewed identity candidate only** into the immutable Trade Scout instrument
master. It does not promote market-data rows and it does not expand the reviewed identity scope.

The current scope is the bounded APTV / AXON / ALLE reviewed seed set. A successful promotion must
still be described as `reviewed_seed_set_only`, not as campaign-wide or S&P 500 identity completion.

## Promotion checks

Before writing canonical instrument-master files, the gate:

1. reloads and structurally validates the persisted private candidate;
2. reloads the checked-in reviewed identity seed configuration;
3. rebuilds the candidate from that seed configuration and the local Tiingo lineage audit;
4. requires the persisted candidate to equal that rebuild exactly;
5. requires zero unresolved reviewed-history coverage gaps;
6. records the seed and lineage-audit SHA-256 digests in immutable promotion provenance;
7. writes canonical instrument and dated symbol-history Parquet files through `InstrumentMasterStore`;
8. reloads the registered snapshot and requires exact equality with the reviewed candidate; and
9. verifies the registered physical Parquet checksums through the normal store load path.

If any of these checks fails, promotion stops without treating the candidate as canonical.

## Operator command

After the v0.2 candidate has been built:

```powershell
uv run python .\scripts\trade_scout_workspace.py promote-tiingo-identity --root "$HOME\trade-scout-private"
```

The command first re-verifies the durable Tiingo receipt/state relationship. It then uses:

```text
<workspace>/evidence/instrument-identity/tiingo-reviewed-candidate.json
<workspace>/evidence/tiingo-lineage/audit.json
configs/tiingo_reviewed_identity_seeds_v0.2.json
```

and writes only identity artifacts under:

```text
<workspace>/canonical-store/canonical/instrument_master/<snapshot>/instruments.parquet
<workspace>/canonical-store/canonical/symbol_history/<snapshot>/symbol_history.parquet
<workspace>/canonical-store/metadata/datasets.duckdb
```

The command reports both logical and physical checksums and explicitly reports
`price_rows_promoted: 0`.

## Idempotency

Re-running the command for an already registered matching snapshot does not create a new version or
change its original registration time. The existing immutable registration is reloaded, its
provenance is compared with the reviewed candidate, and its files are checksum-verified again.

## Non-goals

This gate does not:

- promote Tiingo OHLCV rows;
- accept Tiingo as the primary market-data provider;
- claim identity completeness for the other acquired symbols;
- infer unknown ticker history;
- alter the current S&P 500 universe into a point-in-time historical universe; or
- run features, patterns, rankings, strategies, or trading logic.
