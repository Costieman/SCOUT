# A+B review states v0.1

| State | Meaning | Default action |
|---|---|---|
| `BOTH_AGREE` | Both reviewed provider identities supplied values within tolerance | eligible for promotion policy |
| `BOTH_DISAGREE` | Both supplied the session but at least one OHLCV field differs beyond tolerance | discrepancy review |
| `A_ONLY` | Alpha Vantage supplied the session and Stooq did not | gap/context review |
| `B_ONLY` | Stooq supplied the session and Alpha Vantage did not | gap/context review |

No state authorizes averaging or interpolation.
