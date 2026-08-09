# EODHD Daily-Update Evidence CLI

`write_eodhd_daily_update_evidence.py` is deliberately a narrow serializer/assessment entry point. It accepts prepared canonical-bar JSON slices, applies the EODHD-specific correction-lookback assessment, and emits a strict runtime report. It does not perform provider calls and therefore cannot, by itself, demonstrate live EODHD update behavior.

Use `--live-provider-observation` only when the incoming slice was produced from an actual EODHD retrieval whose raw responses and normalization provenance are retained elsewhere in the runtime evidence chain. The flag is evidence metadata, not a substitute for raw-provider provenance.
