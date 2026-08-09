# Stooq split-semantics evidence

This workflow characterizes how the Stooq daily CSV behaves around externally verified stock-split events. It does not infer corporate actions and it does not promote Stooq to canonical status.

Use several independently verified split cases rather than relying on one security. Each case must include a Stooq query symbol, an explicit reviewed evidence-link ID, the split date, the new-shares-per-old-share ratio, and a bounded date window spanning the event.

Example shape:

```powershell
uv run python scripts/run_stooq_split_semantics_evidence.py `
  --case "SYMBOL.US,reviewed:identity,YYYY-MM-DD,RATIO,YYYY-MM-DD,YYYY-MM-DD"
```

The runner preserves exact provider CSV responses under `runtime/stooq-split-semantics-evidence/raw/` and writes JSON/Markdown reports under the corresponding `report/` directory.

A case is classified as `RAW_LIKE`, `SPLIT_ADJUSTED_LIKE`, or `INCONCLUSIVE`. The comparison is deliberately conservative because ordinary market movement can obscure the mechanical split discontinuity. Multiple consistent, non-inconclusive cases are required before the adjustment-semantics acceptance criterion can be considered for promotion; even then, dividend treatment and broader corporate-action behavior remain separate questions.
