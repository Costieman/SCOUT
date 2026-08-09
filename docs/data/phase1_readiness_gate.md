# Phase 1 combined readiness gate

Phase 1 closes only when two independent conditions are both true:

1. every Data Foundation acceptance criterion is `DEMONSTRATED`; and
2. the selected canonical provider has every provider-acceptance criterion `DEMONSTRATED`.

The combined gate deliberately does not infer provider acceptance from a complete data checklist, or vice versa. This prevents later phases from starting while the historical-data provider remains uncharacterized in areas such as licensing, delistings, corporate actions, retry behavior, secondary reconciliation, or representative-scale canonical ingestion.

Run:

```text
uv run python scripts/run_phase1_readiness.py
```

The command exits with status `0` only when Phase 1 is complete and `2` while blockers remain. Optional output files can be written outside Git with `--output-root`.

The checked-in ledgers remain reviewable project records. Live evidence may support later ledger updates, but the readiness command does not modify either ledger and cannot promote itself.
