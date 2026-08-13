# Provenance-governed research decisions

Trade Scout's strict research-decision boundary now requires the complete validation lineage to reproduce before a decision may be appended.

For every cited `validation-review:<report_id>` reference, the boundary resolves the immutable review from `FileValidationReviewStore`, resolves the matching immutable provenance record from `FileValidationReviewProvenanceStore`, loads the frozen validation plan and checksum-verified source experiment manifest by the identities recorded in provenance, and then rebuilds the provenance binding. If the review used a robustness plan, the corresponding frozen robustness design must also be resolvable.

The decision is not delegated to the existing validation/experiment governance chain unless every provenance binding verifies exactly. Missing provenance, changed validation design, changed experiment manifest or stage-artifact checksum, review replacement, malformed persistence, or unavailable required robustness design therefore fail before any decision-ledger mutation.

## Governance chain

The intended strict path is:

1. immutable experiment definition and source data identity;
2. checksum-verified experiment manifest and stage artifacts;
3. frozen validation and optional robustness design;
4. complete validation evidence and immutable validation review;
5. immutable validation-review provenance binding;
6. provenance reproduction at the decision boundary;
7. validation-review citation and experiment-integrity checks;
8. explicit scientific decision;
9. append-only research-decision ledger.

`ProvenanceGovernedResearchDecisionLedger` implements steps 4–7 as a fail-closed decorator around `ValidationGovernedResearchDecisionLedger`. The latter continues to enforce explicit review/experiment citation and delegates to the existing experiment-integrity-aware decision ledger.

## Scientific boundary

Provenance verification establishes identity, immutability, and lineage. It does not establish that an effect is important, robust in a scientific sense, economically useful, or suitable for production. A complete provenance-verified review may contain null, adverse, unstable, or otherwise unconvincing evidence. The decision state remains an explicit scientific judgment recorded separately.

## Source readers

The boundary depends on narrow read-only protocols rather than a particular persistence implementation:

- `ValidationPlanReader.read_validation_plan(plan_id)`;
- `ExperimentManifestReader.read_manifest(experiment_id)`;
- `RobustnessPlanReader.read_robustness_plan(plan_id)` when a robustness plan is bound.

This keeps provenance enforcement independent of the eventual durable stores for frozen validation and robustness designs while making their identities mandatory at the governance boundary.
