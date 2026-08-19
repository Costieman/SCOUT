# Iterative Research Station read cache

The Research Station is used for repeated neighboring experiments against one selected immutable canonical dataset. Re-reading and re-materializing the same canonical universe on every Run adds latency without changing the evidence base.

This pass adds a process-local read cache around the existing `WindowedCanonicalUniverseResearchSource`. It caches universe discovery, full research-series reads, canonical daily-bar reads, and a bounded LRU of Strategy Builder signal windows. The cache is scoped to the lifetime of the local workbench process, never persists analytical results, never makes provider calls, and can be explicitly cleared.

This optimization is intentionally most valuable for the normal SCOUT workflow: load one suite/brain, run, change one parameter, run again. The first run still pays the canonical read cost; subsequent neighboring runs can reuse identical canonical source material while recomputing entries, exits, metrics, and experiment records from scratch.
