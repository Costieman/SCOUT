# Verified Research Decision Evidence

Research decisions may cite experiment runs only after the persisted experiment evidence has been
verified as intact and the experiment lifecycle is SUCCEEDED.

Use `audit_decision_evidence()` when inspecting a proposed decision. Use
`VerifiedResearchDecisionLedger` for append operations that must fail closed when a cited experiment is
missing, corrupted, unreadable, incomplete, or failed.

This gate verifies persistence integrity and lifecycle completion only. It does not determine whether the
result is statistically significant, scientifically persuasive, economically useful, or eligible for
production. Those remain separate analytical and governance judgments.
