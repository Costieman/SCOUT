# Tiingo / Alpha Vantage targeted gap validation v0.1

## Purpose

The first live review of the proposed thirteen-instrument Tiingo identity slice found a real
coverage discrepancy for Align Technology (`ALGN`). Reviewed lifecycle evidence places public
trading on Nasdaq from 2001-01-26, while the durable Tiingo profile begins on 2001-01-30.
Trade Scout must not move the lifecycle date to fit the provider and must not fabricate the missing
bars.

This probe turns that discrepancy into a bounded independent-provider evidence task. It derives the
missing sessions from the pinned `us-equities-core-full-day-v0.1` XNAS calendar rather than from a
manually maintained date list. For ALGN the derived target sessions are:

- 2001-01-26
- 2001-01-29

The first observed Tiingo session, 2001-01-30, is also requested from the validator as an overlap
anchor.

## Validator boundary

The validator is Alpha Vantage raw `TIME_SERIES_DAILY`. Reaching 2001 requires requesting
`outputsize=full`, which is deliberately behind the explicit operator flag
`--request-alpha-full-history`. The flag requests full output; it does **not** assert that the
account is entitled to it. Provider rejection, quota/authentication failure, or non-observation is
kept distinct from a market-data gap and remains inconclusive.

Exact Alpha Vantage response bytes are retained under the private workspace. The persisted report
contains only dates, counts, provider/provenance identifiers, checksums of already-durable Tiingo
evidence, and status flags. No OHLCV values are written to the public repository or metadata report.

## Operator command

From the repository root, with `ALPHA_VANTAGE_API_KEY` already present in the local environment:

```powershell
uv run python .\scripts\run_tiingo_alpha_targeted_gap_validation.py --root "$HOME\trade-scout-private" --case-id algn-tiingo-initial-coverage-gap-v0.1 --request-alpha-full-history
```

The command first re-verifies the private Tiingo workspace and confirms that the durable profile
still begins ALGN on 2001-01-30. If that evidence changes, validation stops before making the
secondary-provider call.

## Result semantics

`VALIDATOR_PRESENT_READY_FOR_MANUAL_ADJUDICATION` means Alpha Vantage observed both expected gap
sessions and the 2001-01-30 overlap anchor. It does **not** authorize automatic canonical filling.
The raw validator observations still require explicit adjudication and row-level provenance before
any new immutable canonical dataset could be proposed.

`INCONCLUSIVE_VALIDATOR_NONOBSERVATION` means one or more target dates or the anchor were not
observed. Because long-history Alpha Vantage capability is not accepted as complete, absence is not
reclassified as a confirmed market-data gap.

`INCONCLUSIVE_PROVIDER_FAILURE` means the validator request itself failed. Transport,
authentication, entitlement, or quota failures are never treated as missing market sessions.

In every state:

- `canonical_fill_allowed` remains false;
- `price_rows_promoted` remains zero;
- `bars_fabricated` remains zero;
- provider acceptance does not change;
- serving selection does not change.
