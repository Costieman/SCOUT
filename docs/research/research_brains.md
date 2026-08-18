# Research Brains

A SCOUT **research brain** is a focused, append-only collection of immutable experiment references.
It is a research-memory container, not a model, strategy optimizer, automated tuner, or production
promotion mechanism.

## Why this layer exists

The experiment registry records individual runs. A brain adds a narrower question-centered layer on
top of that history: for example, a brain may collect experiments about whether a family of entry
conditions adds information, how a setup behaves in a particular market context, or which related
hypotheses have already failed.

A brain does not have to correspond to one indicator. It should be organized around a coherent
research question. Exit or stop-policy work can belong to a brain when the question and triggering
setup make that relationship explicit rather than treating a stop in isolation as a strategy.

## Evidence preservation

Brain membership is append-only. Successful, failed, null, adverse, and otherwise inconvenient
experiments are preserved. A later view may focus attention on promising configurations, but that
must never delete or rewrite the negative history that explains how the research arrived there.

Each membership binds the exact experiment ID, terminal status, and checksum-verified manifest
checksum that existed when the experiment entered the brain. The brain store can later verify that
the referenced experiment still matches that binding.

## Focus and drift

A brain may declare explicit focus rules against resolved experiment-configuration paths. These are
transparent constraints such as `entry.family=feature_expression`; they are not hidden semantic
classification.

When an experiment violates or lacks a declared focus value, membership is retained with a
`DRIFT_WARNING`. Drift is therefore visible without erasing exploratory boundary challenges. A
brain with no explicit focus rules reports membership as `UNASSESSED` rather than pretending every
experiment is automatically in scope.

The browser calls these rules **focus boundaries** and keeps them under an Advanced section. The
normal workflow does not require users to know configuration paths or technical brain identifiers.
Brain IDs are generated automatically; the question and human-readable name remain the primary UI.

## Browser workflow

The local research workbench exposes `/research/brains` when experiment recording is configured.
The page supports two explicit mutations:

1. Create a brain from a plain-language name and research question, with optional advanced focus
   boundaries.
2. Add an existing terminal experiment record to a selected brain, optionally explaining why it
   belongs there.

Opening, filtering, or inspecting a brain is read-only. Mutations use explicit POST requests, while
all other analytical workbench routes remain GET-only. The page verifies the current experiment
manifest against the checksum/status recorded when the experiment entered the brain and shows an
integrity error rather than silently accepting a mismatch.

The normal UI translates internal scope states into plain language while retaining the exact state:

- `IN_SCOPE`: fits the declared focus.
- `DRIFT_WARNING`: outside one or more declared boundaries; kept in history with a scope warning.
- `UNASSESSED`: no strict focus boundary was available to evaluate it.

## Conditioning boundary

This foundation deliberately does **not** condition or summarize the brain yet. `conditioning_readiness`
is `NOT_ASSESSED`. SCOUT does not infer readiness from an arbitrary fixed count such as five, ten,
or twenty runs.

A later conditioning layer should first assess evidence sufficiency and then synthesize the complete
preserved history. Its output should distinguish what appears to matter, what does not, and which
conclusions are comparatively solid or shaky. Any proposed follow-up experiments must still execute
through the governed experiment system, and any scientific promotion remains subject to the
existing validation and decision boundaries.

Likewise, exchanging knowledge between brains should operate through explicit experiment/evidence
references or governed batches rather than silently merging mutable internal state.

## Private storage

The operator store lives outside the Git repository:

```text
<workspace>/research/brains/
  <brain_id>/
    definition.json
    memberships/
      <experiment_id>.json
```

Definitions and memberships use deterministic canonical JSON and SHA-256 checksums. No market-data
provider calls are made by this layer.

## Operator command

`scripts/research_brain.py` remains available for narrow operator/debug use:

- `create`: create one immutable research question and optional repeated `PATH=VALUE` focus rules;
- `add`: append one checksum-verified terminal experiment from the private experiment store;
- `show`: inspect the complete preserved brain inventory and scope warnings;
- `list`: list available brains with success, failure, drift, and conditioning-readiness counts.

There is intentionally no delete, winner-selection, auto-conditioning, or auto-promotion action in
this slice.
