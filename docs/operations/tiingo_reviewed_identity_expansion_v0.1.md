# Reviewed Tiingo identity expansion v0.1

## Purpose

This workflow widens the proven reviewed pipeline from three instruments to seven without treating
any unreviewed ticker as a permanent identity. It adds four explicitly sourced continuity cases that
are already present in the private durable Tiingo profile:

- `APP` — AppLovin Corporation, Nasdaq trading from 2021-04-15;
- `ABNB` — Airbnb, Inc., Nasdaq trading from 2020-12-10;
- `ANET` — Arista Networks, Inc., NYSE trading from 2014-06-06; and
- `AWK` — American Water Works Company, Inc., current NYSE public listing from 2008-04-23.

The original reviewed cases remain APTV, AXON, and ALLE. The expanded candidate therefore contains
seven permanent internal identities and eleven dated symbol-history intervals.

This is still a bounded engineering sample. It is not campaign-wide identity completeness, Tiingo
provider acceptance, or historical-universe acceptance.

## Evidence policy

The added dates and symbols are backed by issuer or SEC sources checked into the reviewed configs.
The local command does not infer identity from the provider query ticker. Instead it compares the
private durable profile start date with the reviewed lineage case and fails closed if the observed
start differs from the reviewed expectation.

The checked-in versions are:

```text
configs/tiingo_symbol_lineage_cases_v0.2.json
configs/tiingo_reviewed_identity_seeds_v0.3.json
```

The expected local classifications are:

```text
ABNB  CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH
ALLE  WHEN_ISSUED_START_MATCH
ANET  CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH
APP   CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH
APTV  PRE_CURRENT_SYMBOL_HISTORY_OBSERVED
AWK   CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH
AXON  PRE_CURRENT_SYMBOL_HISTORY_OBSERVED
```

Any missing profile case, changed start date, or resulting symbol-history coverage gap blocks the
expanded candidate.

## Build the expanded candidate

From the repository root:

```powershell
uv run python .\scripts\expand_tiingo_reviewed_identity.py --root "$HOME\trade-scout-private"
```

The command makes no provider calls and promotes no price rows. It refreshes the private lineage
audit and writes the expanded candidate to:

```text
<workspace>/evidence/instrument-identity/tiingo-reviewed-candidate.json
```

A successful result must report:

```text
snapshot_version: tiingo-reviewed-identity-candidate-v0.3
instrument_count: 7
symbol_history_count: 11
provider_series_link_count: 7
coverage_gap_count: 0
promotion_ready: true
```

## Promote the expanded identity snapshot

Promotion still uses the existing exact-rebuild gate. Pass the expanded seed config explicitly:

```powershell
uv run python .\scripts\trade_scout_workspace.py promote-tiingo-identity --root "$HOME\trade-scout-private" --config configs/tiingo_reviewed_identity_seeds_v0.3.json
```

This creates a new immutable instrument-master snapshot. The prior v0.2 snapshot remains intact.
Price rows remain zero at this stage.

## Re-run split-only validation

After identity promotion, run the existing preview:

```powershell
uv run python .\scripts\preview_tiingo_split_only.py --root "$HOME\trade-scout-private"
```

The preview now operates over all reviewed Tiingo provider-series links in the current candidate. It
must still pass identity-aware normalization and any eligible zero-dividend vendor-adjusted
cross-checks before canonical price promotion.

## Promote the expanded canonical price slice

The canonical promotion gate now maps reviewed identity snapshots to explicit immutable dataset
versions:

```text
tiingo-reviewed-identity-candidate-v0.2 -> tiingo-reviewed-split-only-v0.1
tiingo-reviewed-identity-candidate-v0.3 -> tiingo-reviewed-split-only-v0.2
```

Run:

```powershell
uv run python .\scripts\promote_tiingo_reviewed_prices.py --root "$HOME\trade-scout-private"
```

The v0.1 three-instrument dataset is never overwritten. The expanded v0.3 identity candidate can
only create the new v0.2 canonical price dataset after all existing fail-closed receipt, identity,
adjustment, and quality gates pass.

## Rebuild the feature snapshot at larger scope

The initial feature command now defaults to the expanded canonical dataset version:

```powershell
uv run python .\scripts\build_initial_feature_slice.py --root "$HOME\trade-scout-private"
```

For reproducibility checks against the original three-instrument slice, pass:

```powershell
uv run python .\scripts\build_initial_feature_slice.py --root "$HOME\trade-scout-private" --dataset-version tiingo-reviewed-split-only-v0.1
```

Derived feature reports include the canonical dataset version in their filename so the original and
expanded evidence are retained separately.

## Boundary

This step deliberately widens only the reviewed sample. It does not assume the remaining acquired
symbols have simple identity histories, does not infer missing lineage, and does not solve
exchange-session completeness. Those remain separate gates before campaign-wide canonical price
promotion or broad strategy conclusions.
