# Persisted Validation Governance

Trade Scout treats statistical validation evidence as an immutable input to scientific governance. A research decision must not depend on a transient Python object that can differ from the review artifact retained for later audit. The persisted validation-governance boundary therefore resolves validation evidence from the checksum-verified validation review store before any decision is appended.

## Canonical evidence references

Validation reviews are cited as `validation-review:<report_id>`. `validation_review_report_id` parses this namespace and rejects empty, whitespace-altered, or path-like report identifiers. Other evidence-reference namespaces remain untouched.

`resolve_persisted_validation_reviews` extracts every validation-review reference from a `ResearchDecision`, requires at least one such reference, rejects duplicates, and loads each report through `FileValidationReviewStore`. A missing, unreadable, schema-incompatible, identity-mismatched, or checksum-invalid review causes the decision path to fail before governance is invoked.

Each successful resolution retains the canonical evidence reference, report ID, verified SHA-256 checksum, and reconstructed `ValidationReviewBundle`. This record is integrity metadata only; it does not interpret the sign, magnitude, confidence interval, p-value, or economic relevance of the evidence.

## Governance chain

`PersistedValidationGovernedResearchDecisionLedger` composes the persistence boundary with the existing validation and experiment gates in a fixed order:

1. resolve every cited validation review from immutable persistence and verify its checksum;
2. pass those reconstructed review bundles to `ValidationGovernedResearchDecisionLedger`, which checks completeness and explicit decision/review/experiment linkage;
3. delegate to `VerifiedResearchDecisionLedger`, which verifies every cited experiment is intact and `SUCCEEDED`;
4. append the explicit decision to the checksum-verified, append-only research decision ledger.

A failure at an earlier boundary prevents later mutation. In particular, a corrupt validation review cannot reach the decision ledger, even if the decision object itself is otherwise well formed.

## Scientific boundary

Persistence and linkage are not scientific acceptance criteria. A complete holdout result may be null or adverse and still be a valid review artifact. The governance chain preserves such evidence rather than filtering it. The eventual `REJECTED`, `INCONCLUSIVE`, `CANDIDATE`, `VALIDATED`, or `PRODUCTION-ELIGIBLE` state remains an explicit, attributable research decision with its own rationale and promotion constraints.

The current persistence contract establishes artifact integrity, not independent proof that a review bundle was originally assembled from the correct frozen validation plan. That stronger provenance relation remains a separate validation-orchestration concern and should not be inferred merely from a valid checksum.
