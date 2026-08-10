from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    configure_operator_workspace,
    initialize_operator_workspace,
    load_operator_workspace,
    verify_operator_workspace,
    workspace_status_payload,
)
from trade_scout.data.providers.tiingo_campaign_state import (
    initial_tiingo_safe_campaign_state,
    persist_tiingo_safe_campaign_state,
)
from trade_scout.data.providers.tiingo_sp500_campaign import TiingoSp500UniverseSnapshot


def test_initialize_workspace_creates_private_layout_and_safe_manifest(tmp_path: Path) -> None:
    root = tmp_path / "trade-scout-private"
    created = datetime(2026, 8, 10, 6, 0, tzinfo=UTC)

    workspace = initialize_operator_workspace(
        root,
        storage_namespace="private-ssd-v1",
        workspace_id="phase1-test",
        created_at=created,
    )

    assert workspace.root == root.resolve()
    assert workspace.tiingo_raw_root.is_dir()
    assert workspace.tiingo_receipts_root.is_dir()
    assert workspace.composite_evidence_root.is_dir()
    assert workspace.corporate_action_evidence_root.is_dir()
    assert workspace.failed_ingestion_root.is_dir()
    assert workspace.canonical_root.is_dir()

    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert payload["workspace_id"] == "phase1-test"
    assert payload["storage_namespace"] == "private-ssd-v1"
    assert "token" not in json.dumps(payload).lower()
    assert "api_key" not in json.dumps(payload).lower()


def test_initialize_is_idempotent_but_rejects_unrelated_nonempty_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    first = initialize_operator_workspace(root, storage_namespace="ns-a")
    second = initialize_operator_workspace(root, storage_namespace="ns-a")
    assert first.manifest == second.manifest

    with pytest.raises(OperatorWorkspaceError, match="another storage namespace"):
        initialize_operator_workspace(root, storage_namespace="ns-b")

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "notes.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(OperatorWorkspaceError, match="non-empty directory"):
        initialize_operator_workspace(unrelated, storage_namespace="ns-c")


def test_workspace_discovers_only_explicit_evidence_locations(tmp_path: Path) -> None:
    workspace = initialize_operator_workspace(tmp_path / "workspace", storage_namespace="ns")
    repository = tmp_path / "repo"
    (repository / "configs").mkdir(parents=True)
    (repository / "configs" / "provider_acceptance_tiingo_v0.1.json").write_text(
        "{}", encoding="utf-8"
    )
    (repository / "configs" / "provider_acceptance_free_stack_v0.1.json").write_text(
        "{}", encoding="utf-8"
    )

    (workspace.composite_evidence_root / "b.json").write_text("{}", encoding="utf-8")
    (workspace.composite_evidence_root / "a.json").write_text("{}", encoding="utf-8")
    (workspace.composite_evidence_root / "ignore.txt").write_text("x", encoding="utf-8")
    (workspace.corporate_action_evidence_root / "actions.json").write_text(
        "{}", encoding="utf-8"
    )
    (workspace.failed_ingestion_root / "job.failed").write_text("x", encoding="utf-8")

    sources = workspace.data_health_sources(repository_root=repository)

    assert [path.name for path in sources.composite_evidence_paths] == ["a.json", "b.json"]
    assert [path.name for path in sources.corporate_action_anomaly_reports] == ["actions.json"]
    assert [path.name for path in sources.failed_ingestion_markers] == ["job.failed"]
    assert sources.tiingo_safe_state_path is None
    assert sources.canonical_root is None
    assert sources.canonical_dataset_version is None


def test_configure_persists_explicit_canonical_and_freshness_selection(tmp_path: Path) -> None:
    workspace = initialize_operator_workspace(tmp_path / "workspace", storage_namespace="ns")
    configured = configure_operator_workspace(
        workspace,
        canonical_dataset_version="canonical-v7",
        scanner_required_session=date(2026, 8, 7),
    )
    loaded = load_operator_workspace(configured.root)

    assert loaded.manifest.canonical_dataset_version == "canonical-v7"
    assert loaded.manifest.scanner_required_session == date(2026, 8, 7)


def test_verification_fails_closed_when_state_claims_completion_without_receipt(
    tmp_path: Path,
) -> None:
    workspace = initialize_operator_workspace(tmp_path / "workspace", storage_namespace="ns")
    snapshot = TiingoSp500UniverseSnapshot(
        snapshot_date=date(2026, 8, 10),
        symbols=("AAPL", "MSFT"),
        sha256="a" * 64,
    )
    state = initial_tiingo_safe_campaign_state(
        campaign_id="tiingo-sp500-baseline-v0.1",
        plan_version="plan-v1",
        snapshot=snapshot,
    )
    state = replace(state, durable_completed_symbols=("AAPL",))
    persist_tiingo_safe_campaign_state(workspace.tiingo_safe_state_path, state)

    report = verify_operator_workspace(workspace)

    assert report.is_consistent is False
    assert report.durable_completed_symbol_count == 1
    assert report.missing_receipt_symbols == ("AAPL",)
    assert report.verified_receipt_count == 0


def test_empty_workspace_is_consistent_and_status_contains_no_market_values(tmp_path: Path) -> None:
    workspace = initialize_operator_workspace(tmp_path / "workspace", storage_namespace="ns")
    report = verify_operator_workspace(workspace)
    status = workspace_status_payload(workspace)

    assert report.is_consistent is True
    assert report.state_present is False
    assert status["tiingo"] == {
        "state_present": False,
        "status": "NOT_STARTED",
        "durable_completed_symbol_count": 0,
        "total_symbol_count": None,
        "durable_row_count_total": 0,
        "quota_pause_count": 0,
        "failure_count": 0,
        "last_run_at": None,
    }
    assert status["verification"]["consistent"] is True
