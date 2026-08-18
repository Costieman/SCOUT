# Research Brain follow-up execution

Research Brain follow-up execution is the first bridge from **remembered evidence** to an actual new
governed experiment. It deliberately keeps planning, approval, and execution as separate actions.

## Lifecycle

A follow-up must pass three explicit gates:

1. **Draft** — Brain Conditioning freezes the current evidence priority into an immutable proposal.
2. **Approve** — the researcher approves that exact proposal. Approval alone remains
   `APPROVED_NOT_RUN`.
3. **Execute** — an implemented executor re-verifies the approval and current brain state, then
   launches one normal Experiment Runner child experiment.

There is no implied authorization to execute future proposals. If brain membership changes after a
proposal is drafted, that proposal is stale and cannot be executed. If an execution receipt already
exists, repeated execution requests return the existing receipt instead of launching a second run.

## Executor v1: randomized eligible-timing comparator

The first implemented executor handles `COMPARATOR` proposals for feature-expression Strategy
Builder research. It uses the existing canonical data source, Strategy Builder semantics, generic
exit engine, Experiment Runner, experiment registry, and Research Brain store.

The comparator asks a narrow question:

> Does the frozen source entry timing add information beyond count-matched randomized eligible
> timing on the same instruments under the same holding-period and execution-cost assumptions?

For every instrument represented in the complete source event population, the control preserves
that instrument's event count and samples alternative eligible signal dates from the same canonical
series. It performs 1,000 deterministic randomizations and records:

- source hold-to-horizon mean return;
- randomized-timing mean return;
- excess versus randomized timing;
- empirical 95% null interval;
- one-sided empirical p-value;
- source sample size and instrument count;
- eligible timing count;
- random seed and comparator definition version.

This comparator preserves **instrument counts**, not the exact original market-date or regime mix.
It is therefore useful timing-control evidence, not a complete matched market/sector/regime control.
The p-value is exploratory and is not adjusted for the broader strategy search.

## Parameter-sweep sources

A saved parameter sweep is a search surface, not an executable single strategy definition. SCOUT
therefore refuses to choose the historical maximum automatically.

Before executing the comparator, the operator must choose one candidate value that was already in
the source sweep's immutable `declared_values`. The executor freezes that value into the source
parameterized feature definition. Values outside the original sweep are rejected rather than
silently widening the search.

## Provenance and persistence

The child experiment:

- is `EXPLORATORY`;
- uses the currently selected immutable dataset and no provider calls;
- records the source experiment as `parent_experiment_id`;
- records proposal and approval checksums in its resolved configuration;
- records the deterministic random seed and comparator inputs;
- is indexed by the normal experiment registry;
- is automatically appended to the same Research Brain when terminal.

A failed child is also retained and appended to the brain so failure history is not lost.

Each execution creates a checksum-verified receipt under:

```text
<workspace>/research/brains/<brain_id>/proposal-executions/<proposal_id>.json
```

The receipt binds the proposal checksum, approval checksum, execution inputs, terminal child
experiment ID/checksum/status, researcher, and timestamp.

## Unsupported proposal kinds

Executor v1 does **not** approximate other proposal types. Uncertainty, multiplicity, unseen-data,
time-stability, parameter-stability, and formal-validation proposals can still be drafted and
approved, but the browser states that no execution adapter exists yet.

This is intentional. Each evidence challenge needs its own governed analytical workflow rather than
a generic button that silently changes the scientific question.

## Scientific boundary

A successful comparator run does not validate or promote a strategy. It adds one explicit control
to the brain's evidence. The conditioning map may then move to the next missing evidence dimension,
but production eligibility continues to require the existing formal validation and decision
boundaries.
