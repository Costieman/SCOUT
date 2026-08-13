# Validation Evidence to Research Governance

Trade Scout separates statistical validation from research promotion. A complete validation review bundle is evidence for a decision; it is not itself a decision.

## Why this boundary exists

The experiment-governance layer already verifies that experiments cited by a `ResearchDecision` are intact and completed successfully. The statistical-validation layer now provides a stronger object: `ValidationReviewBundle`, which proves that the frozen validation design was represented completely and preserves the corresponding uncertainty, comparator, multiplicity, robustness, and parameter-surface evidence.

Without an explicit bridge, a decision could cite an opaque artifact string without demonstrating that the cited validation review belongs to one of the decision's experiments. `validation_decision_evidence` closes that gap without converting evidence into a score or state transition.

## Canonical review references

`validation_review_reference(bundle)` emits `validation-review:<report_id>`. A governed decision must contain that exact reference in `ResearchDecision.evidence_references`, and the review bundle's `experiment_id` must also appear in the decision's `experiment_ids`.

`audit_validation_decision_evidence` records, for every supplied review bundle:

- canonical evidence reference;
- report, experiment, validation-plan, and primary-outcome identities;
- evidence and warning counts;
- validation-completeness state;
- whether the experiment is cited by the decision; and
- whether the canonical review reference is cited by the decision.

It also detects validation-review references named by the decision for which no bundle was supplied. Duplicate review IDs and duplicate canonical validation-review references are rejected.

## Fail-closed governance composition

`ValidationGovernedResearchDecisionLedger` decorates the existing `VerifiedResearchDecisionLedger`. Its append path first requires validation-review evidence to verify, then delegates to the existing persisted-experiment integrity check and append-only decision ledger.

The resulting sequence is therefore:

1. run and persist experiments;
2. validate their outputs under a frozen time-ordered design;
3. assemble a complete `ValidationReviewBundle`;
4. explicitly cite that review bundle in a human-authored `ResearchDecision`;
5. verify the review-to-decision linkage;
6. verify the underlying experiment manifests and integrity; and
7. append the immutable research decision.

## Scientific boundary

No function in this bridge interprets effect size, p-value, confidence interval, parameter surface, robustness result, or warning count as evidence for a particular `ResearchDecisionState`. A bundle with adverse or null results can be perfectly admissible evidence. The reviewer remains responsible for choosing and explaining `REJECTED`, `INCONCLUSIVE`, `CANDIDATE`, `VALIDATED`, or `PRODUCTION-ELIGIBLE`, subject to the separate supersession and production-attestation rules.
