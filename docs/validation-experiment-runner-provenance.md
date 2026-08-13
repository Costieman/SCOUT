# Experiment Runner validation provenance

`ExperimentRunnerGovernedValidationWorkflow` is the strict execution path for validation that uses
Experiment Runner child manifests.

A successful receipt requires a checksum-verified successful source experiment, one durable child
experiment for every frozen validation target, a complete persisted validation review, persisted
review provenance, and a persisted ordered child-provenance binding. The child binding connects the
review-provenance checksum to every child manifest and its stage-artifact checksums and is rebuilt
from persisted manifests before success is returned.

This workflow records execution lineage only. It does not choose a preferred parameter set, infer
scientific credibility, or assign a research-decision state. If the final child binding cannot be
built or verified, the workflow raises `ValidationExecutionError`. Earlier immutable artifacts may
remain for audit purposes, but they do not constitute a successful completed workflow without the
final receipt.

The generic `GovernedValidationWorkflow` remains available for synthetic tests and alternate
executors that do not produce Experiment Runner child manifests. Concrete Experiment Runner
validation should use the strict workflow so child provenance cannot be omitted accidentally.
