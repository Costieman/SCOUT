# Experiment Runner validation adapter

Trade Scout's governed validation workflow now has a concrete bridge to the normal `ExperimentRunner`. Each frozen validation target can be executed as its own durable child experiment rather than being satisfied by an opaque in-memory calculation.

`ExperimentRunnerValidationTargetExecutor` resolves and verifies the successful source experiment, delegates target-specific analytical construction to a `ValidationTargetExperimentFactory`, freezes the validation target identity into reserved child configuration metadata, executes the child through `ExperimentRunner`, rereads the persisted stage artifacts, and delegates evidence construction to a `ValidationEvidenceExtractor`.

The child experiment is explicitly linked to the source through `parent_experiment_id`. Research mode, code version, and configuration-schema version must remain unchanged. Dataset-version drift is rejected except for a predeclared `DATASET_REVISION` robustness target. Universe-version drift requires the frozen target to declare a changed `universe.*` field. Production-monitoring mode is never admissible for validation children.

## Analytical boundary

The generic adapter deliberately does not interpret `changed_fields` as executable mutation instructions. A field such as `costs`, `entry_convention`, or `patterns.duration_sessions` has domain-specific semantics that belong in an explicit analytical factory. Automatically rewriting configuration from those strings would create hidden research logic in the orchestration layer and could silently change the scientific question.

Similarly, the evidence extractor must derive its `EvidenceSnapshot` from the completed child manifest and persisted stage outputs. The adapter then rechecks the evidence role and intrinsic walk-forward/robustness identity before returning it to the completeness workflow.

## Reproducibility boundary

This layer establishes a durable Experiment Runner record for every validation target and ensures that the evidence is derived after those child artifacts have been persisted. The existing review provenance record still binds the completed review to the root source experiment manifest. It does not yet cryptographically enumerate every validation child manifest. That stronger child-lineage binding remains a separate provenance extension and should not be inferred from this adapter alone.

The adapter makes no scientific promotion decision. A completely reproduced child experiment can still produce null, adverse, unstable, or otherwise unpersuasive evidence.
