from __future__ import annotations

import pytest

from trade_scout.data.import_orchestrator import (
    AssetImportEvidence,
    ImportOrchestrator,
    ImportStage,
    ImportTerminalState,
)


def test_promoted_asset_is_terminal_and_does_not_repeat_work() -> None:
    evidence = AssetImportEvidence(
        symbol="AAPL",
        acquired=True,
        structurally_validated=True,
        identity_verified=True,
        identity_registered=True,
        reconciled=True,
        complete=True,
        promoted=True,
    )

    plan = ImportOrchestrator().plan(evidence)

    assert plan.next_stage is None
    assert plan.terminal_state is ImportTerminalState.PROMOTED
    assert plan.reason == "already canonical"


def test_genuinely_missing_asset_returns_acquire_only() -> None:
    plan = ImportOrchestrator().plan(AssetImportEvidence(symbol="MSFT"))

    assert plan.next_stage is ImportStage.ACQUIRE
    assert plan.terminal_state is None


def test_asset_resumes_from_first_incomplete_downstream_stage() -> None:
    evidence = AssetImportEvidence(
        symbol="NVDA",
        acquired=True,
        structurally_validated=True,
        identity_verified=True,
        identity_registered=True,
    )

    plan = ImportOrchestrator().plan(evidence)

    assert plan.next_stage is ImportStage.RECONCILE


def test_deferred_identity_case_does_not_block_other_assets() -> None:
    orchestrator = ImportOrchestrator()
    plans = orchestrator.plan_many(
        [
            AssetImportEvidence(
                symbol="BAC",
                acquired=True,
                structurally_validated=True,
                deferred_reason="lineage requires adjudication",
            ),
            AssetImportEvidence(
                symbol="AAPL",
                acquired=True,
                structurally_validated=True,
                identity_verified=True,
                identity_registered=True,
                reconciled=True,
                complete=True,
            ),
        ]
    )

    assert plans[0].symbol == "AAPL"
    assert plans[0].next_stage is ImportStage.PROMOTE
    assert plans[1].symbol == "BAC"
    assert plans[1].terminal_state is ImportTerminalState.DEFERRED


def test_summary_accounts_for_terminal_and_active_population() -> None:
    orchestrator = ImportOrchestrator()
    summary = orchestrator.summarize(
        [
            AssetImportEvidence(
                symbol="AAPL",
                acquired=True,
                structurally_validated=True,
                identity_verified=True,
                identity_registered=True,
                reconciled=True,
                complete=True,
                promoted=True,
            ),
            AssetImportEvidence(
                symbol="BAC",
                acquired=True,
                structurally_validated=True,
                deferred_reason="lineage requires adjudication",
            ),
            AssetImportEvidence(
                symbol="XYZ",
                acquired=True,
                quarantine_reason="structural corruption",
            ),
            AssetImportEvidence(symbol="MSFT"),
        ]
    )

    assert summary.total_assets == 4
    assert summary.terminally_accounted_for == 3
    assert summary.remaining == 1
    assert summary.terminal_counts[ImportTerminalState.PROMOTED] == 1
    assert summary.terminal_counts[ImportTerminalState.DEFERRED] == 1
    assert summary.terminal_counts[ImportTerminalState.QUARANTINED] == 1
    assert summary.next_stage_counts[ImportStage.ACQUIRE] == 1


def test_invalid_stage_chain_fails_closed() -> None:
    with pytest.raises(ValueError, match="reconciliation"):
        AssetImportEvidence(
            symbol="JPM",
            acquired=True,
            structurally_validated=True,
            identity_verified=True,
            identity_registered=True,
            reconciled=False,
            complete=True,
        )


def test_duplicate_symbols_are_rejected() -> None:
    orchestrator = ImportOrchestrator()

    with pytest.raises(ValueError, match="duplicate symbols"):
        orchestrator.plan_many(
            [AssetImportEvidence(symbol="AAPL"), AssetImportEvidence(symbol="AAPL")]
        )
