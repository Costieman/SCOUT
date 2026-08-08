# Research data contract

Downstream research modules consume `ResearchBar` records rather than provider-native objects or storage-specific rows. A `ResearchDataRequest` states the immutable canonical dataset version, date range, price representation, and permitted research quality states.

## Serving rules

- Every bar inside the requested date range must belong to the requested dataset version. A mismatch fails explicitly rather than being silently filtered or replaced.
- The caller supplies point-in-time eligibility for every served instrument/session. Missing eligibility fails; the data layer never assumes that a security was historically eligible.
- Raw versus split-adjusted prices are selected explicitly through `PriceRepresentation`. If the requested representation is unavailable, the existing canonical contract fails rather than falling back to another price basis.
- `PASS` and, when explicitly requested, `WARN` are the only quality states that can reach normal research serving. `QUARANTINE` and `REJECT` cannot be enabled through the serving request.
- Duplicate canonical instrument/session keys fail at the boundary.
- Output is deterministically ordered and retains `instrument_id`, trading date, OHLC, volume, point-in-time eligibility, quality status, immutable dataset version, and declared price representation.

The contract intentionally includes ineligible observations with `eligibility=False` rather than silently changing the statistical sample. A downstream research module decides how its registered universe uses that flag.

The contract test suite includes a downstream consumer that imports and consumes `ResearchBar` without importing any provider adapter or provider-native staging object. This demonstrates the vendor-independent boundary required before feature implementation can safely begin.
