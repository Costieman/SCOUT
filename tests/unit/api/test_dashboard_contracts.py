from datetime import UTC, date, datetime

import pytest

from trade_scout.api.dashboard_contracts import (
    ApplicationSnapshot,
    DataHealthSummary,
    EvidenceSummary,
    HealthState,
    ProvenanceSummary,
    QualityCounts,
    ResearchLabSummary,
    ResearchState,
    ScannerCandidateSummary,
    ScannerSummary,
    WorkspaceState,
)


def _provenance() -> ProvenanceSummary:
    return ProvenanceSummary(
        dataset_version=None,
        strategy_version=None,
        feature_set_version=None,
        risk_policy_version=None,
        ranking_model_version=None,
        run_id=None,
        as_of_date=None,
    )


def test_research_launch_cannot_be_enabled_with_blockers() -> None:
    with pytest.raises(ValueError, match="blocking reasons"):
        ResearchLabSummary(
            workspace_state=WorkspaceState.PREVIEW,
            strategy_family="consolidation breakout",
            universe_label="US equities",
            dataset_label="dataset",
            research_mode=ResearchState.EXPLORATORY,
            resolved_configuration_id="cfg-1",
            launch_enabled=True,
            blocking_reasons=("dataset not accepted",),
            provenance=_provenance(),
        )


def test_blocked_scanner_cannot_expose_candidate_rows() -> None:
    candidate = ScannerCandidateSummary(
        instrument_id="instrument-1",
        symbol="TEST",
        company_name="Synthetic Test",
        candidate_state="TRIGGER_READY",
        strategy_version="strategy-v1",
        pattern_duration_sessions=20,
        distance_to_trigger_fraction=0.01,
        evidence=EvidenceSummary(
            sample_size=100,
            positive_outcome_fraction=0.55,
            uncertainty_low=0.45,
            uncertainty_high=0.65,
            expectancy=0.02,
            mae_median=-0.03,
            mfe_median=0.05,
        ),
        risk_summary="synthetic",
        data_freshness=HealthState.PASS,
        transparent_rank_value=None,
        provenance=_provenance(),
    )
    with pytest.raises(ValueError, match="blocked scanner"):
        ScannerSummary(
            workspace_state=WorkspaceState.BLOCKED,
            as_of_date=date(2026, 8, 10),
            freshness_gate=HealthState.BLOCKED,
            candidates=(candidate,),
            blocking_reasons=("freshness gate failed",),
            provenance=_provenance(),
        )


def test_probability_contract_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        EvidenceSummary(
            sample_size=10,
            positive_outcome_fraction=1.2,
            uncertainty_low=0.2,
            uncertainty_high=0.8,
            expectancy=None,
            mae_median=None,
            mfe_median=None,
        )


def test_application_snapshot_requires_timezone_aware_generation_time() -> None:
    health = DataHealthSummary(
        state=HealthState.BLOCKED,
        dataset_version=None,
        latest_canonical_session=None,
        quality_counts=QualityCounts(0, 0, 0),
        missing_data_anomaly_count=0,
        cross_provider_discrepancy_count=0,
        corporate_action_anomaly_count=0,
        failed_ingestion_job_count=0,
        scanner_freshness_gate=HealthState.BLOCKED,
        providers=(),
        message="blocked",
        provenance=_provenance(),
    )
    research = ResearchLabSummary(
        workspace_state=WorkspaceState.PREVIEW,
        strategy_family="consolidation breakout",
        universe_label="US equities",
        dataset_label="not accepted",
        research_mode=ResearchState.EXPLORATORY,
        resolved_configuration_id=None,
        launch_enabled=False,
        blocking_reasons=("blocked",),
        provenance=_provenance(),
    )
    scanner = ScannerSummary(
        workspace_state=WorkspaceState.BLOCKED,
        as_of_date=None,
        freshness_gate=HealthState.BLOCKED,
        candidates=(),
        blocking_reasons=("blocked",),
        provenance=_provenance(),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        ApplicationSnapshot(
            generated_at=datetime(2026, 8, 10, 5, 0),
            build_label="test",
            active_phase="Phase 1",
            data_health=health,
            research=research,
            scanner=scanner,
            experiments=(),
            global_notices=(),
        )

    valid = ApplicationSnapshot(
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        build_label="test",
        active_phase="Phase 1",
        data_health=health,
        research=research,
        scanner=scanner,
        experiments=(),
        global_notices=(),
    )
    assert valid.generated_at.utcoffset() is not None
