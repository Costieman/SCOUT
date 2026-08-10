"""Compose the replaceable application snapshot from read-only application services."""

from __future__ import annotations

from datetime import datetime

from trade_scout.api.dashboard_contracts import (
    ApplicationSnapshot,
    DataHealthSummary,
    HealthState,
    ResearchLabSummary,
    ResearchState,
    ScannerSummary,
    WorkspaceState,
)


def build_phase1_application_snapshot(
    data_health: DataHealthSummary,
    *,
    generated_at: datetime,
    build_label: str,
) -> ApplicationSnapshot:
    """Build a Phase 1 UI snapshot without inventing analytical or market outputs."""

    dataset_label = data_health.dataset_version or "Approved canonical dataset required"
    research_blockers = [
        "Research controls must be generated from validated configuration schemas before launch."
    ]
    if data_health.dataset_version is None:
        research_blockers.insert(0, "Phase 1 canonical data-foundation acceptance is incomplete.")

    scanner_blockers: list[str] = []
    if data_health.dataset_version is None:
        scanner_blockers.append("No accepted canonical dataset has been selected.")
    if data_health.scanner_freshness_gate is not HealthState.PASS:
        scanner_blockers.append("Scanner freshness gate is not PASS.")
    scanner_blockers.append(
        "Validated production-eligible strategy definitions are required before candidate output."
    )

    research = ResearchLabSummary(
        workspace_state=WorkspaceState.PREVIEW,
        strategy_family="Consolidation breakout",
        universe_label="S&P 500 Phase 1 research universe",
        dataset_label=dataset_label,
        research_mode=ResearchState.EXPLORATORY,
        resolved_configuration_id=None,
        launch_enabled=False,
        blocking_reasons=tuple(research_blockers),
        provenance=data_health.provenance,
    )
    scanner = ScannerSummary(
        workspace_state=WorkspaceState.BLOCKED,
        as_of_date=data_health.latest_canonical_session,
        freshness_gate=data_health.scanner_freshness_gate,
        candidates=(),
        blocking_reasons=tuple(scanner_blockers),
        provenance=data_health.provenance,
    )
    notices = ["DATA HEALTH is evidence-backed; Research and Scanner remain intentionally gated."]
    if data_health.dataset_version is None:
        notices.append("No canonical Phase 1 dataset has been promoted for this snapshot.")

    return ApplicationSnapshot(
        generated_at=generated_at,
        build_label=build_label,
        active_phase="Phase 1 · Data Foundation",
        data_health=data_health,
        research=research,
        scanner=scanner,
        experiments=(),
        global_notices=tuple(notices),
    )
