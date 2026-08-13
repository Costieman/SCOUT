# Governed validation execution

Trade Scout treats validation as an auditable research workflow rather than an implicit post-processing step. The governed validation workflow begins from immutable validation and robustness plans, resolves a checksum-verified source experiment manifest, executes every declared validation target exactly once, assembles complete evidence, persists the review, and writes the provenance binding required by the strict research-decision boundary.

## Execution model

A frozen `ValidationPlan` expands deterministically into segment and walk-forward targets. A frozen `RobustnessPlan`, when supplied, adds one target for every predeclared robustness challenge. Target order is retained as development/validation/holdout segments, walk-forward folds, then robustness challenges. The orchestration layer checks that target identities are unique before any analytical work proceeds.

Each target is passed to a `ValidationTargetExecutor`. This is deliberately an adapter boundary: implementations may invoke the normal Experiment Runner, a stage-specific research adapter, or another deterministic analytical implementation. The executor computes evidence; it does not control which targets exist, whether target coverage is complete, or how evidence is persisted.

Returned snapshots must match the target's required evidence role. Walk-forward targets must return the exact `fold_id`, and robustness targets must return the exact `challenge_id`. A target cannot quietly satisfy another target, and duplicate evidence identities fail closed.

## Governed workflow

`GovernedValidationWorkflow` resolves the selected validation plan, optional robustness plan, and source experiment manifest from their persistence interfaces. The source experiment must be `SUCCEEDED` and checksum-bearing before validation can begin. If the validation plan declares robustness checks, the supplied frozen robustness plan must contain the same challenge identities in the same order.

After analytical execution, the workflow builds a `ValidationEvidenceReport` and uses the existing completeness gate to require exact coverage of all segments, folds, and robustness challenges. It then persists the immutable `ValidationReviewBundle`, builds the cryptographic provenance binding against the frozen design and source manifest, and persists that provenance record. The returned receipt records the report identity, source experiment and plan identities, target count, review checksum, and provenance checksum.

## Scientific boundary

This workflow establishes completeness, identity, reproducibility, and lineage. It does not determine whether an observed effect is scientifically persuasive, does not choose a preferred parameter configuration, and does not assign `CANDIDATE`, `VALIDATED`, production eligibility, or any other research-decision state. Those remain explicit governance decisions after evidence review.

## Failure semantics

The workflow fails before downstream persistence when frozen sources cannot be resolved, the source experiment is not successful, robustness declarations differ, or an executor returns evidence with the wrong role or intrinsic identity. Review persistence and provenance persistence are append-only. A later retry must therefore use a new report identity if a durable review has already been written.
