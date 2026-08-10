# A+B completion checklist v0.1

The implementation is considered structurally complete when:

- Alpha Vantage and Stooq are isolated behind provider adapters.
- both raw response streams can be preserved immutably;
- reviewed identities are required before comparison;
- the union of sessions is classified as agreement, disagreement, A-only, or B-only;
- field-level disagreements remain visible;
- one-sided coverage is measurable rather than silently filled;
- no canonical dataset is written by the evidence runner;
- a bounded GitHub Actions workflow can execute the comparison using the Alpha Vantage secret and current Stooq CSV access;
- unit/integration tests pass in CI.

Live-data acceptance remains separate from structural completion. A representative live run must still be reviewed before any one-sided promotion policy is enabled.
