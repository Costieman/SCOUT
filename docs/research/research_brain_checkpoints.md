# Research Brain Review Checkpoints

A review checkpoint is an explicit immutable snapshot of what one Research Brain review said at one
moment. It exists so later conditioning can reason about how the evidence changed over time rather
than seeing only the brain's latest state.

## What a checkpoint freezes

Each checkpoint records:

- research brain ID and checksum of the immutable brain definition;
- exact experiment memberships present at that moment;
- checksum of every membership record;
- exact experiment-manifest checksum bound to each membership;
- the deterministic descriptive `ResearchBrainReview` payload;
- checkpoint creator, timestamp, note, ID, and schema version.

The checkpoint does not copy market data or recompute research. Experiment manifests and artifacts
remain the underlying evidence.

## Explicit mutation boundary

Viewing a brain or generating its current descriptive review remains read-only. A checkpoint is
created only through an explicit `Save review checkpoint` POST action in the local workbench or the
corresponding application-service method.

This distinction matters: changing pages, filters, or display state cannot silently alter research
memory. The user deliberately decides when a descriptive state is worth preserving.

## Append-only history

Checkpoints live under the private brain store:

```text
<workspace>/research/brains/<brain_id>/reviews/
  brainreview_...json
```

Each JSON document is canonicalized and checksum-verified. A later experiment may be appended to the
brain, but that does not rewrite an earlier checkpoint. The store can explicitly test whether an old
checkpoint still matches the brain's current membership state.

## Scientific boundary

A saved checkpoint is **not**:

- a validated research conclusion;
- a candidate or production strategy;
- an optimum-parameter declaration;
- a multiplicity correction;
- an out-of-sample or walk-forward result;
- an automatic conditioning event;
- a reason to delete negative evidence.

It freezes a descriptive evidence summary, nothing more.

## Why this matters for later conditioning

Future conditioning should be able to answer questions such as:

- What did this brain know before the latest experiments were added?
- Which apparent relationships persisted across successive evidence checkpoints?
- Did a previously interesting parameter region weaken after a comparator or larger sample was added?
- Did the brain's scope drift as unrelated experiments accumulated?

Those questions are safer to answer from immutable checkpoints than from mutable conversational memory.
The next conditioning layer should therefore consume checkpoints plus the underlying experiments and add
explicit evidence-quality assessment before suggesting follow-up research.
