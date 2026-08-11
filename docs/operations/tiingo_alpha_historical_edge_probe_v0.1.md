# Tiingo / Alpha Vantage historical edge probe v0.1

## Purpose

The recent complementarity campaign showed complete, agreeing Tiingo and Alpha Vantage coverage for
AAPL, MSFT, NVDA, AMZN, JPM, XOM, KO, and CAT over 2026-04-01 through 2026-08-07. That validates the
comparison machinery but does not test the historical edges where a composite free dataset could add
coverage.

This probe moves directly to the reviewed Align Technology (`ALGN`) initial-history discrepancy. The
reviewed lifecycle begins on 2001-01-26, while the durable Tiingo profile previously began on
2001-01-30. Under the pinned XNAS calendar the reviewed gap sessions are 2001-01-26 and 2001-01-29;
2001-01-30 is the overlap anchor.

## GitHub-only probe

The manual workflow `Tiingo Alpha historical edge probe` uses the existing `TIINGO_API_TOKEN` and
`ALPHA_VANTAGE_API_KEY` repository secrets. Tiingo is queried only for 2001-01-26 through 2001-01-30.
Alpha Vantage is explicitly requested with `outputsize=full` because compact output cannot reach 2001.
The request does not assume that the configured Alpha Vantage account is entitled to full output.

Provider payloads remain in memory and are not uploaded. The Actions artifact contains dates,
classification states, field names for any overlap disagreement, and safety metadata only; it does
not contain OHLCV values.

## Interpretation

`SECONDARY_CONFIRMS_PRIMARY_GAP` requires both reviewed gap sessions to be observed by Alpha Vantage
but not Tiingo, plus agreement between providers on the 2001-01-30 anchor. This is strong evidence that
Alpha Vantage can complement the known Tiingo edge, but it still does not authorize automatic
canonical filling.

`PRIMARY_COVERAGE_CHANGED` means Tiingo now observes at least one reviewed gap session. The stored
Tiingo coverage evidence must then be re-profiled rather than relying on the earlier gap finding.

`ANCHOR_DISAGREEMENT` means Alpha Vantage observes the reviewed gap sessions but disagrees with Tiingo
on the overlap anchor. The candidate gap remains unresolved pending review.

`INCONCLUSIVE_SECONDARY_NONOBSERVATION` means Alpha Vantage did not observe every reviewed gap session.
Because Alpha long-history completeness is not accepted, absence is not proof that no bar existed.

`INCONCLUSIVE_ALPHA_FULL_HISTORY_UNAVAILABLE` means the configured Alpha Vantage account rejected or
could not satisfy the full-history request. This is an entitlement/capability result rather than a
market-data result.

In every state:

- canonical gap filling remains disabled;
- no provider values are averaged or voted on;
- no raw bar is fabricated or interpolated;
- no provider is promoted or selected for serving;
- no canonical price row is written.
