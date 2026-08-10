from datetime import UTC, date, datetime

from trade_scout.api.dashboard_contracts import (
    ApplicationSnapshot,
    DataHealthSummary,
    HealthState,
    ProvenanceSummary,
    ProviderHealthSummary,
    QualityCounts,
    ResearchLabSummary,
    ResearchState,
    ScannerSummary,
    WorkspaceState,
)
from trade_scout.app.operational_surface import render_operational_application_html


def test_operational_surface_shows_campaign_progress_and_blockers() -> None:
    provenance = ProvenanceSummary(
        dataset_version=None,
        strategy_version=None,
        feature_set_version=None,
        risk_policy_version=None,
        ranking_model_version=None,
        run_id=None,
        as_of_date=None,
        software_version="test",
    )
    health = DataHealthSummary(
        state=HealthState.BLOCKED,
        dataset_version=None,
        latest_canonical_session=None,
        quality_counts=QualityCounts(0, 0, 0),
        missing_data_anomaly_count=3,
        cross_provider_discrepancy_count=1,
        corporate_action_anomaly_count=None,
        failed_ingestion_job_count=0,
        scanner_freshness_gate=HealthState.BLOCKED,
        providers=(
            ProviderHealthSummary(
                provider_id="tiingo",
                display_name="Tiingo",
                role="Long-history baseline candidate",
                state=HealthState.WARN,
                latest_successful_session=date(2026, 8, 7),
                message="candidate",
                progress_current=2,
                progress_total=3,
                progress_label="durably secured symbols",
                operational_status="PAUSED_RATE_LIMITED",
                last_observed_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
                quota_pause_count=2,
                failure_count=0,
                last_rate_limited_symbol="AAPL",
            ),
        ),
        message="blocked",
        provenance=provenance,
        review_work_item_count=4,
        phase_blockers=("Secondary validation remains incomplete.",),
    )
    snapshot = ApplicationSnapshot(
        generated_at=datetime(2026, 8, 10, 5, 1, tzinfo=UTC),
        build_label="test",
        active_phase="Phase 1",
        data_health=health,
        research=ResearchLabSummary(
            workspace_state=WorkspaceState.PREVIEW,
            strategy_family="Consolidation breakout",
            universe_label="S&P 500",
            dataset_label="required",
            research_mode=ResearchState.EXPLORATORY,
            resolved_configuration_id=None,
            launch_enabled=False,
            blocking_reasons=("blocked",),
            provenance=provenance,
        ),
        scanner=ScannerSummary(
            workspace_state=WorkspaceState.BLOCKED,
            as_of_date=None,
            freshness_gate=HealthState.BLOCKED,
            candidates=(),
            blocking_reasons=("blocked",),
            provenance=provenance,
        ),
        experiments=(),
        global_notices=(),
    )

    html = render_operational_application_html(snapshot)

    assert "Phase 1 control plane" in html
    assert "Secondary validation remains incomplete." in html
    assert "2/3 durably secured symbols" in html
    assert "66.7%" in html
    assert "PAUSED_RATE_LIMITED" in html
    assert "AAPL" in html
    assert "Cross-provider review work</dt><dd>4" in html
