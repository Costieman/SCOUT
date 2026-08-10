from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from trade_scout.api.dashboard_contracts import HealthState
from trade_scout.app.data_health_service import (
    DataHealthSourcePaths,
    build_data_health_summary,
)
from trade_scout.data.providers.tiingo_campaign_state import (
    initial_tiingo_safe_campaign_state,
    persist_tiingo_safe_campaign_state,
)
from trade_scout.data.providers.tiingo_sp500_campaign import TiingoSp500UniverseSnapshot


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _tiingo_acceptance(path: Path) -> Path:
    return _write_json(
        path,
        {
            "decision": "CANDIDATE_NOT_ACCEPTED",
            "criteria": [],
        },
    )


def _free_stack(path: Path) -> Path:
    return _write_json(
        path,
        {
            "criteria": [
                {
                    "criterion": "alpha_vantage_point_in_time_listing_status",
                    "note": "Alpha bounded validation evidence is available.",
                },
                {
                    "criterion": "stooq_historical_ohlcv_retrieval",
                    "note": "Stooq automated retrieval remains operationally constrained.",
                },
            ]
        },
    )


def test_data_health_reads_durable_tiingo_campaign_state(tmp_path: Path) -> None:
    snapshot = TiingoSp500UniverseSnapshot(
        snapshot_date=date(2026, 8, 10),
        symbols=("AAPL", "MSFT", "JPM"),
        sha256="a" * 64,
    )
    state = initial_tiingo_safe_campaign_state(
        campaign_id="tiingo-sp500-baseline-v0.1",
        plan_version="plan-v1",
        snapshot=snapshot,
    )
    state_path = tmp_path / "safe-state.json"
    persist_tiingo_safe_campaign_state(state_path, state)

    health = build_data_health_summary(
        DataHealthSourcePaths(
            tiingo_acceptance_path=_tiingo_acceptance(tmp_path / "tiingo.json"),
            free_stack_acceptance_path=_free_stack(tmp_path / "free-stack.json"),
            tiingo_safe_state_path=state_path,
        )
    )

    tiingo = health.providers[0]
    assert health.state is HealthState.BLOCKED
    assert health.dataset_version is None
    assert tiingo.progress_current == 0
    assert tiingo.progress_total == 3
    assert "durable campaign 0/3" in tiingo.message
    assert health.missing_data_anomaly_count is None
    assert health.cross_provider_discrepancy_count is None


def test_data_health_aggregates_only_supplied_composite_evidence(tmp_path: Path) -> None:
    evidence_path = _write_json(
        tmp_path / "composite.json",
        {
            "cases": [
                {
                    "summary": {
                        "row_count": 10,
                        "both_agree_count": 6,
                        "both_disagree_count": 2,
                        "a_only_count": 1,
                        "b_only_count": 1,
                    }
                },
                {
                    "summary": {
                        "row_count": 5,
                        "both_agree_count": 4,
                        "both_disagree_count": 0,
                        "a_only_count": 1,
                        "b_only_count": 0,
                    }
                },
            ]
        },
    )

    health = build_data_health_summary(
        DataHealthSourcePaths(
            tiingo_acceptance_path=_tiingo_acceptance(tmp_path / "tiingo.json"),
            free_stack_acceptance_path=_free_stack(tmp_path / "free-stack.json"),
            composite_evidence_paths=(evidence_path,),
        )
    )

    assert health.missing_data_anomaly_count == 3
    assert health.cross_provider_discrepancy_count == 2
    assert health.corporate_action_anomaly_count is None
    assert health.failed_ingestion_job_count is None


def test_missing_canonical_selection_never_looks_fresh(tmp_path: Path) -> None:
    health = build_data_health_summary(
        DataHealthSourcePaths(
            tiingo_acceptance_path=_tiingo_acceptance(tmp_path / "tiingo.json"),
            free_stack_acceptance_path=_free_stack(tmp_path / "free-stack.json"),
            scanner_required_session=date(2026, 8, 7),
        )
    )

    assert health.scanner_freshness_gate is HealthState.BLOCKED
    assert health.latest_canonical_session is None
