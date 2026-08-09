# Current reference reconciliation

Reference sources such as SEC EDGAR can improve issuer metadata and provide independent evidence about current ticker/exchange associations, but they do not automatically solve permanent security identity.

The reconciliation layer therefore produces **review candidates only**. It does not call `link_provider_identity`, create canonical `InstrumentId` values, overwrite market-provider metadata, or infer historical symbol continuity.

## Matching policy

- Current market and reference symbols must agree exactly after case/whitespace normalization.
- Symbol punctuation is not rewritten. For example, `BRK.B` and `BRK-B` are not assumed equivalent without a provider-specific reviewed mapping.
- Exchange agreement strengthens a candidate; a unique symbol with exchange disagreement is retained only as weaker evidence.
- Multiple matching reference rows remain `AMBIGUOUS`.
- Missing company names do not prevent a candidate when symbol/exchange evidence is otherwise exact. This allows SEC reference data to help investigate the blank-name cases observed in historical Alpha Vantage listing snapshots without fabricating a market-provider name.
- Name agreement is supporting metadata only and never becomes an identity key.

## Temporal rule

Current ticker-association files must not be back-projected into historical market snapshots. The current-reference reconciler therefore rejects any request carrying a historical `market_as_of` date. Historical identity requires dated provider evidence or an explicitly reviewed identity-history source.

## Promotion rule

A unique reference candidate is still not a canonical provider link. Promotion into the instrument master requires a separate reviewed identity decision with evidence sufficient to justify the link. This preserves the project rule that ticker is display/history metadata rather than permanent identity.
