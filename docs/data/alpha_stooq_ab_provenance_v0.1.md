# A+B provenance requirements v0.1

Every composite evidence row retains the canonical `instrument_id`, trade date, both provider IDs, the observed provider bars, the coverage/disagreement state, and differing field names where applicable. Exact source payload provenance remains in each provider's immutable raw store.

The composite layer is intentionally evidence-only. It must be possible to trace a reviewed promotion back to the provider observation and raw retrieval batch without reconstructing or mutating provider history.
