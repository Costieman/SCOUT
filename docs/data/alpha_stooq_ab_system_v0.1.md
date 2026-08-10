# Alpha Vantage + Stooq A+B system v0.1

The A+B system is the first operational composite-evidence layer for the free-data foundation.

## What it does

For explicitly reviewed instrument identities and bounded date ranges, it retrieves raw daily OHLCV independently from Alpha Vantage and Stooq, preserves both raw payload streams, and classifies the union of observed sessions as:

- `BOTH_AGREE`
- `BOTH_DISAGREE`
- `A_ONLY`
- `B_ONLY`

It reports corroborated coverage, one-sided coverage, and field-level disagreement. This creates the evidence needed to decide where the combined Trade Scout dataset is more complete than either provider alone.

## What it does not do

The A+B evidence layer does not write a canonical dataset, average provider values, interpolate missing sessions, infer identity links, or treat two-provider agreement as proof that a value is historically correct.

Only `BOTH_AGREE` rows are marked `canonicalizable_without_review=true`. One-sided observations require gap/context review before promotion. Disagreements require explicit discrepancy review.

## Operational path

The manual GitHub Actions workflow `Alpha + Stooq composite evidence` accepts one or more reviewed cases. It uses the repository Alpha Vantage secret and Stooq's current CSV endpoint, writes raw responses only to ignored runtime storage, and uploads only the non-secret evidence report.

## Next acceptance step

Run representative cases spanning ordinary active securities, known split periods, sparse/edge cases, and inactive/delisted history where both providers can be queried. Review the resulting one-sided and disagreement states before enabling any canonical promotion policy.
