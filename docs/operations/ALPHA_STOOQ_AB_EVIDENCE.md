# Alpha Vantage + Stooq A+B live evidence

## Workflow

Run `Alpha + Stooq composite evidence` manually after the branch is merged.

For the initial smoke evaluation, supply:

`SPY,SPY.US,instrument:spy,stooq:spy,2026-01-02,2026-03-31;AAPL,AAPL.US,instrument:aapl,stooq:aapl,2026-01-02,2026-03-31`

The workflow requires the existing `ALPHA_VANTAGE_API_KEY` repository secret. Stooq uses the public bounded CSV endpoint and requires no repository secret in the current adapter.

## Evidence output

The uploaded report contains only classifications and comparison metadata. Raw Alpha Vantage and Stooq responses remain under ignored runtime paths and are deliberately excluded from the workflow artifact.

Do not enable canonical one-sided fill from this smoke run. First inspect `A_ONLY`, `B_ONLY`, and `BOTH_DISAGREE` rows and determine whether they reflect real provider gaps, calendars, listing state, identity mapping, or adjustment semantics.
