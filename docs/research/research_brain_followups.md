# Research Brain Follow-Up Proposals

Research Brain follow-up proposals turn the brain's current evidence-quality priority into an
explicit, reviewable research plan. They are the bridge between **SCOUT suggesting what should be
challenged next** and a later governed execution layer.

This layer does **not** execute research.

## Sequence

The intended lifecycle is:

```text
saved experiments
  -> Research Brain memory
  -> descriptive review
  -> evidence-quality conditioning
  -> follow-up proposal
  -> explicit operator approval
  -> later governed execution
  -> new immutable experiment evidence
```

Proposal creation and approval are deliberately separate from execution. Clicking **Draft next
experiment** stores a plan. Clicking **Approve plan — do not run** stores consent to that exact plan.
Neither action launches a Strategy Builder run, validation job, provider request, or any other
analytical calculation.

## Proposal identity

Each proposal is immutable and binds:

- the Research Brain ID and checksum of its immutable definition;
- the exact brain-membership set and membership checksums;
- the exact experiment-manifest checksums present when the proposal was drafted;
- the conditioning version and conditioning priority that motivated the proposal;
- one checksum-verified successful source experiment;
- the source experiment manifest checksum;
- the checksum of the source experiment's resolved configuration;
- the proposed hypothesis, frozen elements, one intended change, required operator inputs, and
  readiness state.

The proposal ID is deterministic for the same material brain/evidence state. Drafting again before
the evidence changes therefore returns the same proposal rather than manufacturing duplicate plans.

## Stale plans

A proposal becomes **STALE** when the Research Brain definition or experiment-membership history no
longer matches the state on which it was based. A stale proposal remains visible for history, but it
cannot be approved.

This is important because a suggestion that made sense before another experiment was added may no
longer be the correct next evidence challenge. SCOUT requires a fresh proposal instead of silently
reinterpreting the old one against new evidence.

## Approval boundary

Approval is a separate append-only record bound to the proposal checksum. The browser labels an
approved plan **APPROVED — NOT RUN**.

Approval means only:

> this exact research plan is an acceptable next challenge to execute later.

It does not mean:

- the source result is credible or validated;
- the proposal is a candidate or production strategy;
- the proposed hypothesis is expected to succeed;
- a parameter value has been selected as an optimum;
- an experiment has been launched.

## Proposal types

Conditioning v1 can draft the following challenge types from the existing evidence map:

- **Comparator** — hold the source definition fixed and add one predeclared baseline/control.
- **Uncertainty** — retain the source definition and add an approved uncertainty/dependence method.
- **Parameter stability** — challenge the already-declared neighboring sweep values around the
  observed peak without widening the search merely to find a better result.
- **Multiplicity** — register the complete searched family and apply the appropriate search/multiple-
  testing treatment before formal inference.
- **Out of sample** — freeze the source definition and require an unseen interval to be declared
  before execution.
- **Time stability** — freeze the source definition and require a predeclared time-ordered/walk-
  forward design.
- **Formal validation review** — when no obvious evidence-coverage gap remains, stop exploratory
  tuning by default and decide whether the compact hypothesis is ready for the existing governed
  validation workflow.

Some proposals are `READY_TO_PLAN`; others are `OPERATOR_INPUT_REQUIRED` because SCOUT must not invent
scientific choices such as the comparator, holdout window, walk-forward schedule, or multiplicity
method after seeing results. A formal validation handoff is `GOVERNED_REVIEW_REQUIRED`.

## Source experiment rule

The first implementation chooses the latest readable **SUCCEEDED** experiment already attached to
the brain as the frozen source definition. Failed experiments remain in brain history and continue
to influence the descriptive/conditioning context, but they are not executable source definitions.

A later refinement may expose explicit source selection where multiple successful definitions are
scientifically plausible. That should remain an explicit choice rather than an automatic
profit-ranked selection.

## Future executor

The follow-up executor is intentionally not part of this slice. When implemented, it should:

1. accept only an approved, non-stale proposal;
2. re-verify the proposal, approval, brain membership, source manifest, dataset and configuration
   identity;
3. refuse execution while required operator inputs remain unresolved;
4. translate the approved plan into the existing Experiment Runner or governed validation workflow
   rather than creating a parallel backtester;
5. create a new immutable experiment with explicit parent/proposal lineage;
6. attach the completed experiment back to the originating brain only through an explicit governed
   action;
7. preserve failures as research evidence.

No executor should allow an approval to become a standing permission for autonomous parameter
search. Every material new plan must have its own frozen proposal and approval.

## Storage

Private operator state is colocated with the brain:

```text
<workspace>/research/brains/<brain_id>/
  proposals/
    <proposal_id>.json
  proposal-approvals/
    <proposal_id>.json
```

Both proposal and approval envelopes are canonical-JSON, checksum-verified, append-only records.

## Scientific boundary

This feature helps SCOUT move from **"what evidence is missing?"** to **"here is the next controlled
question I would test"**. It does not answer the question, execute it, or turn research history into
a strategy recommendation.

That separation preserves the project rule: quantify first, challenge the result, preserve what
survives, and only then decide what deserves validation or production use.
