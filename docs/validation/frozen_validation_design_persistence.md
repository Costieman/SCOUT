# Frozen validation design persistence

Trade Scout treats confirmatory validation design as evidence-bearing research configuration. A validation plan or robustness plan must therefore be recoverable later as the exact design that existed before confirmatory outcomes were interpreted.

`FileValidationPlanStore` and `FileRobustnessPlanStore` provide append-only filesystem persistence for these frozen designs. Each plan is serialized deterministically, wrapped in a schema-versioned envelope, protected by a SHA-256 payload checksum, and written atomically. Reusing an existing plan identity is rejected rather than overwriting the prior design.

Reads fail closed on missing or unreadable files, unsupported schema versions, file/payload identity mismatches, checksum changes, malformed payloads, or violations of the typed validation contracts. The validation-plan store preserves development/validation/holdout segments, walk-forward folds, primary outcome, comparator identity, robustness-check declarations, and notes. The robustness store preserves challenge identity, kind, description, and changed fields.

The stores implement the reader contracts used by provenance-governed research decisions: `read_validation_plan(plan_id)` and `read_robustness_plan(plan_id)`. This means a decision boundary can resolve the same checksum-verified frozen design that was cryptographically bound to its persisted validation review, rather than relying on an in-memory reconstruction.

Checksum integrity establishes that the retained design has not changed. It does not establish that the original scientific design was appropriate, that its thresholds were well chosen, or that favorable evidence warrants promotion. Those remain explicit scientific review decisions.
