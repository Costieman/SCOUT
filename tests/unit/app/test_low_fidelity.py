from datetime import UTC, datetime

from trade_scout.api.dashboard_contracts import (
    ApplicationSnapshot,
    DataHealthSummary,
    HealthState,
    ProviderHealthSummary,
    ProvenanceSummary,
    QualityCounts,
    ResearchLabSummary,
    ResearchState,
    ScannerSummary,
    WorkspaceState,
)
from trade_scout.app.low_fidelity import render_application_html


def _snapshot() -> ApplicationSnapshot:
    provenance = ProvenanceSummary(
        dataset_version=None,
        strategy_version=None,
        feature_set_version=None,
        risk_policy_version=None,
        ranking_model_version=None,
        run_id=None,
        as_of_date=None,
        software_version="test-build",
    )
    return ApplicationSnapshot(
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        build_label="wireframe-test",
        active_phase="Phase 1 · Data Foundation",
        data_health=DataHealthSummary(
            state=HealthState.BLOCKED,
            dataset_version=None,
            latest_canonical_session=None,
            quality_counts=QualityCounts(0, 0, 0),
            missing_data_anomaly_count=0,
            cross_provider_discrepancy_count=0,
            corporate_action_anomaly_count=0,
            failed_ingestion_job_count=0,
            scanner_freshness_gate=HealthState.BLOCKED,
            providers=(
                ProviderHealthSummary(
                    provider_id="provider-test",
                    display_name="Provider <Test>",
                    role="candidate",
                    state=HealthState.WARN,
                    latest_successful_session=None,
                    message="not accepted",
                ),
            ),
            message="data foundation incomplete",
            provenance=provenance,
        ),
        research=ResearchLabSummary(
            workspace_state=WorkspaceState.PREVIEW,
            strategy_family="Consolidation breakout",
            universe_label="US equities",
            dataset_label="approved dataset required",
            research_mode=ResearchState.EXPLORATORY,
            resolved_configuration_id=None,
            launch_enabled=False,
            blocking_reasons=("data foundation incomplete",),
            provenance=provenance,
        ),
        scanner=ScannerSummary(
            workspace_state=WorkspaceState.BLOCKED,
            as_of_date=None,
            freshness_gate=HealthState.BLOCKED,
            candidates=(),
            blocking_reasons=("validated strategy required",),
            provenance=provenance,
        ),
        experiments=(),
        global_notices=("DESIGN PREVIEW",),
    )


def test_renderer_exposes_required_workspaces_and_provenance() -> None:
    html = render_application_html(_snapshot())

    for label in (
        "Research Lab",
        "Market Scanner",
        "Experiment Library",
        "Data Health",
        "Alerts",
        "System / Project",
        "Provenance",
    ):
        assert label in html
    assert "Research first · Validate second · Scan third · Alert last" in html


def test_renderer_keeps_blocked_outputs_visibly_blocked() -> None:
    html = render_application_html(_snapshot())

    assert "No normal candidate rows available." in html
    assert "Launch</dt><dd>BLOCKED" in html
    assert "validated strategy required" in html
    assert "No notification controls are enabled" in html


def test_renderer_escapes_user_facing_values_and_has_no_trade_execution_controls() -> None:
    html = render_application_html(_snapshot())

    assert "Provider &lt;Test&gt;" in html
    assert "Provider <Test>" not in html
    forbidden = ("Place order", "Buy now", "Sell now", "Execute trade")
    assert not any(label in html for label in forbidden)
