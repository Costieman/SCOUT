# Alpha Vantage + Stooq review queue v0.1

The A+B evidence system now separates corroborated observations from work that still requires explicit review.

`BOTH_AGREE` rows bypass the review queue because the two providers corroborate raw OHLCV within the configured tolerance. `A_ONLY` and `B_ONLY` rows enter the queue as gap reviews. `BOTH_DISAGREE` rows enter the queue as discrepancy reviews and retain the fields that differ.

Each review item receives a deterministic `review_id` derived from canonical instrument identity, trade date, both provider identities, evidence state, and differing fields. Re-running the same evidence therefore produces the same review identifier; a changed evidence state produces a different identifier rather than silently reusing an old decision.

A completed review batch must resolve every queued item exactly once. Permitted reviewed outcomes are `PRIMARY_ACCEPTED`, `SECONDARY_ACCEPTED`, or `REJECTED`, and each resolution requires a non-empty audit note. Missing, duplicate, or extraneous resolutions block adjudication.

The live Alpha Vantage + Stooq evidence runner now emits the review queue alongside coverage statistics in `composite-evidence.json`. This makes a live run directly actionable: corroborated rows are immediately identifiable, while every gap or disagreement has a stable work item that can be investigated before composite canonical promotion.

The review queue does not infer truth, perform provider voting, interpolate a missing bar, or select a one-sided observation automatically.
