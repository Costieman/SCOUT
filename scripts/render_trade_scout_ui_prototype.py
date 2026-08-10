"""Render the low-fidelity Trade Scout application shell without a web framework.

The preview intentionally represents the current Phase 1 gating posture rather than inventing
market candidates or research results. It is a design fixture, not a live dashboard.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/ui-prototype/index.html"),
    )
    args = parser.parse_args()
    snapshot = _phase1_preview_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_application_html(snapshot), encoding="utf-8")
    print(args.output)
    return 0


def _phase1_preview_snapshot() -> ApplicationSnapshot:
    no_production_provenance = ProvenanceSummary(
        dataset_version=None,
        strategy_version=None,
        feature_set_version=None,
        risk_policy_version=None,
        ranking_model_version=None,
        run_id=None,
        as_of_date=None,
        software_version="0.1.0.dev0",
    )
    data_health = DataHealthSummary(
        state=HealthState.BLOCKED,
        dataset_version=None,
        latest_canonical_session=None,
        quality_counts=QualityCounts(passed=0, warned=0, quarantined=0),
        missing_data_anomaly_count=0,
        cross_provider_discrepancy_count=0,
        corporate_action_anomaly_count=0,
        failed_ingestion_job_count=0,
        scanner_freshness_gate=HealthState.BLOCKED,
        providers=(
            ProviderHealthSummary(
                provider_id="tiingo",
                display_name="Tiingo",
                role="Long-history baseline candidate",
                state=HealthState.WARN,
                latest_successful_session=None,
                message="Credential and historical-depth probes passed; primary acceptance remains gated.",
            ),
            ProviderHealthSummary(
                provider_id="alpha_vantage",
                display_name="Alpha Vantage",
                role="Independent validation / listings evidence",
                state=HealthState.WARN,
                latest_successful_session=None,
                message="Useful bounded validator; free-tier history and request limits constrain scale.",
            ),
            ProviderHealthSummary(
                provider_id="stooq",
                display_name="Stooq",
                role="Opportunistic/manual third observation",
                state=HealthState.BLOCKED,
                latest_successful_session=None,
                message="Automated CSV transport encountered browser-verification protection.",
            ),
        ),
        message="No canonical Phase 1 baseline dataset has been accepted yet.",
        provenance=no_production_provenance,
    )
    research = ResearchLabSummary(
        workspace_state=WorkspaceState.PREVIEW,
        strategy_family="Consolidation breakout",
        universe_label="Liquid US-listed equities (planned)",
        dataset_label="Approved canonical dataset required",
        research_mode=ResearchState.EXPLORATORY,
        resolved_configuration_id=None,
        launch_enabled=False,
        blocking_reasons=(
            "Phase 1 data-foundation acceptance is not complete.",
            "Research controls must be generated from validated configuration schemas before launch.",
        ),
        provenance=no_production_provenance,
    )
    scanner = ScannerSummary(
        workspace_state=WorkspaceState.BLOCKED,
        as_of_date=None,
        freshness_gate=HealthState.BLOCKED,
        candidates=(),
        blocking_reasons=(
            "Scanner output is downstream of validated strategy definitions and an accepted fresh dataset.",
            "No synthetic candidate rows are shown as if they were market observations.",
        ),
        provenance=no_production_provenance,
    )
    return ApplicationSnapshot(
        generated_at=datetime.now(UTC),
        build_label="low-fidelity-v0.1",
        active_phase="Phase 1 · Data Foundation",
        data_health=data_health,
        research=research,
        scanner=scanner,
        experiments=(),
        global_notices=(
            "DESIGN PREVIEW — not a live market-data dashboard.",
            "Current phase gate is visible by design: Research can be previewed; Scanner and Alerts remain blocked.",
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
