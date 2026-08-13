# Validation Review Provenance

Trade Scout treats a persisted statistical validation review as an auditable scientific artifact, but review integrity alone is not sufficient to establish lineage. A valid review checksum proves that the retained review payload has not changed. It does not, by itself, prove which frozen validation design or experiment artifacts were used when the review was assembled.

`ValidationReviewProvenance` closes that gap by binding one review identity and checksum to the exact validation-plan checksum, checksum-verified experiment manifest, ordered stage-artifact checksums, and, when applicable, the robustness-plan checksum. The binding is deterministic and can be reproduced later from the same frozen sources.

`build_validation_review_provenance` fails closed unless the review identifies the supplied validation plan and experiment, the source experiment succeeded, the experiment-manifest checksum reproduces exactly, and the review's completeness assessment can be independently recomputed from its evidence assignments against the supplied validation and robustness plans. This means a caller cannot create provenance merely by pairing unrelated valid artifacts.

`FileValidationReviewProvenanceStore` persists each lineage record once using canonical JSON, an envelope schema version, and a SHA-256 payload checksum. Existing report IDs cannot be overwritten. Reads reject malformed JSON, unsupported schema versions, report-identity mismatches, invalid digest fields, and checksum tampering.

`verify_validation_review_provenance` re-reads the persisted review, verifies its current checksum, rebuilds the complete provenance record from the supplied frozen plan and checksum-verified experiment manifest, and requires exact equality with the retained lineage record. Changes to the validation design, source manifest, stage-artifact checksums, robustness design, or review payload therefore invalidate the binding.

The resulting chain is:

`frozen validation design + checksum-verified experiment/stage evidence -> complete validation review -> immutable review checksum -> immutable provenance binding -> explicit scientific governance`

This layer remains intentionally narrower than a scientific decision rule. A provenance-valid review may contain null, unstable, or adverse evidence. Cryptographic lineage establishes what evidence and design were reviewed; it does not establish that the evidence supports promotion or production eligibility.
