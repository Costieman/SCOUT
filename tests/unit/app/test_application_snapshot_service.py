from datetime import UTC, datetime

from trade_scout.api.dashboard_contracts import (
    DataHealthSummary,
    HealthState,
    ProvenanceSummary,
    QualityCounts,
    WorkspaceState,
)
from trade_scout.app.application_snapshot_service import build_phase1_application_snapshot


def test_application_snapshot_keeps_research_and_scanner_gated_without_dataset() -> None:
    provenance = ProvenanceSummary(
        dataset_version=None,
        strategy_version=None,
        feature_set_version=None,
        risk_policy_version=None,
        ranking_model_version=None,
        run_id=None,
        as_of_date=None,
    )
    health = DataHealthSummary(
        state=HealthState.BLOCKED,
        dataset_version=None,
        latest_canonical_session=None,
        quality_counts=QualityCounts(0, 0, 0),
        missing_data_anomaly_count=None,
        cross_provider_discrepancy_count=None,
        corporate_action_anomaly_count=None,
        failed_ingestion_job_count=None,
        scanner_freshness_gate=HealthState.BLOCKED,
        providers=(),
        message="No canonical dataset.",
        provenance=provenance,
    )

    snapshot = build_phase1_application_snapshot(
        health,
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        build_label="test",
    )

    assert snapshot.research.workspace_state is WorkspaceState.PREVIEW
    assert snapshot.research.launch_enabled is False
    assert snapshot.scanner.workspace_state is WorkspaceState.BLOCKED
    assert snapshot.scanner.candidates == ()
    assert any("No canonical" in item for item in snapshot.global_notices)
