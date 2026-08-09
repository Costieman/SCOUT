# EODHD Daily-Update Evidence

Phase 1 requires deterministic incremental updates to be demonstrated with provider evidence, not inferred from generic revision tests.

The EODHD-specific assessment layer compares one immutable canonical parent dataset with an incoming correction-lookback slice and records appended, revised, unchanged-overlap, and carried-forward observations. The report schema also records whether the incoming slice came from a live EODHD request. Synthetic or provider-neutral observations therefore remain useful engineering evidence but cannot be mistaken for a live provider demonstration.

A live operational runner is still required to close this criterion. That runner must obtain the overlap window from EODHD, normalize it through the same canonical data path, assess it against the prior immutable dataset version, persist the report under `runtime/`, and retain the raw provider responses used to support the update assessment.

The acceptance ledger must remain `PARTIAL` until that live cycle is executed and reviewed.
