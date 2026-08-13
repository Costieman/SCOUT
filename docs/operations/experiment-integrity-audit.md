# Experiment integrity audit

Trade Scout experiment manifests are authoritative reproducibility records only while their persisted content remains verifiable. The experiment integrity audit provides a fail-closed check over the manifest and every small stage artifact referenced by it.

## Audit boundary

`audit_experiment(store, experiment_id)` first loads the experiment manifest through the normal checksum-verifying store. If the manifest is missing, malformed, or fails its checksum, the audit reports a manifest failure and does not treat any stage evidence as verified.

When the manifest verifies, each recorded stage artifact is re-read through the `ManifestStore` contract and its deterministic JSON checksum is recomputed. Stage state is reported as `VERIFIED`, `MISSING`, `CHECKSUM_MISMATCH`, or `UNREADABLE`.

`ExperimentIntegrityReport.require_verified()` raises when any part of the persisted record is not intact. Future reproduce/audit commands should use this boundary before claiming that historical experiment evidence is reproducible from the stored record.

## Non-responsibilities

The integrity audit does not assess statistical validity, economic significance, parameter stability, production eligibility, or whether an experiment's scientific conclusion is justified. It verifies persistence integrity only.

## Tests

Synthetic tests cover intact experiments, missing stage artifacts, tampered stage content, corrupted manifests, malformed JSON artifacts, and delegation through `IndexedManifestStore`.
