from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.app.data_health_service import DataHealthSourcePaths
from trade_scout.app.local_console import (
    LocalConsoleConfig,
    LocalConsoleConfigurationError,
    build_console_response,
    validate_bind_host,
)


def _write_sources(tmp_path: Path) -> DataHealthSourcePaths:
    tiingo = tmp_path / "tiingo.json"
    tiingo.write_text(
        json.dumps(
            {
                "assessment_version": "test-tiingo-v0.1",
                "provider_id": "tiingo",
                "decision": "CANDIDATE_NOT_ACCEPTED",
                "criteria": [],
            }
        ),
        encoding="utf-8",
    )
    free_stack = tmp_path / "free-stack.json"
    free_stack.write_text(
        json.dumps(
            {
                "assessment_version": "test-free-stack-v0.1",
                "criteria": [
                    {
                        "criterion": "alpha_vantage_point_in_time_listing_status",
                        "status": "PARTIAL",
                        "note": "Alpha validation evidence is bounded.",
                    },
                    {
                        "criterion": "stooq_historical_ohlcv_retrieval",
                        "status": "PARTIAL",
                        "note": "Stooq automated transport is not accepted.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return DataHealthSourcePaths(
        tiingo_acceptance_path=tiingo,
        free_stack_acceptance_path=free_stack,
    )


def _config(tmp_path: Path) -> LocalConsoleConfig:
    return LocalConsoleConfig(
        sources=_write_sources(tmp_path),
        build_label="local-test-v0.1",
        refresh_seconds=9,
    )


def test_index_is_evidence_backed_and_auto_refreshes(tmp_path: Path) -> None:
    response = build_console_response(
        "/",
        _config(tmp_path),
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert '<meta http-equiv="refresh" content="9">' in html
    assert "Data Health" in html
    assert "Phase 1 control plane" in html
    assert "What is blocking the data foundation?" in html
    assert "CANDIDATE_NOT_ACCEPTED" in html
    assert "Cross-provider reconciliation evidence has not been supplied." in html
    assert "No explicitly selected canonical Phase 1 dataset is available." in html
    assert ("Cache-Control", "no-store") in response.headers
    assert any(name == "Content-Security-Policy" for name, _ in response.headers)


def test_data_health_json_preserves_unknown_metrics_as_null(tmp_path: Path) -> None:
    response = build_console_response(
        "/api/data-health.json",
        _config(tmp_path),
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["state"] == "BLOCKED"
    assert payload["missing_data_anomaly_count"] is None
    assert payload["cross_provider_discrepancy_count"] is None
    assert payload["review_work_item_count"] is None
    assert payload["failed_ingestion_job_count"] is None
    assert payload["providers"][0]["provider_id"] == "tiingo"
    assert payload["providers"][0]["operational_status"] == "STATE_NOT_SUPPLIED"
    assert payload["phase_blockers"]


def test_snapshot_api_exposes_gates_without_candidates(tmp_path: Path) -> None:
    response = build_console_response(
        "/api/snapshot.json",
        _config(tmp_path),
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["research"]["launch_enabled"] is False
    assert payload["scanner"]["workspace_state"] == "BLOCKED"
    assert payload["scanner"]["candidates"] == []
    assert payload["generated_at"] == "2026-08-10T05:00:00+00:00"


def test_healthz_reports_application_gate_not_provider_connectivity(tmp_path: Path) -> None:
    response = build_console_response(
        "/healthz",
        _config(tmp_path),
        generated_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload == {
        "data_health_state": "BLOCKED",
        "dataset_version": None,
        "generated_at": "2026-08-10T05:00:00+00:00",
        "phase_blocker_count": 5,
        "review_work_item_count": None,
        "scanner_freshness_gate": "BLOCKED",
        "service": "trade-scout-local-console",
        "status": "ok",
    }


def test_unknown_route_is_404_without_loading_provider_data(tmp_path: Path) -> None:
    response = build_console_response("/no-such-route", _config(tmp_path))
    payload = json.loads(response.body)

    assert response.status_code == 404
    assert payload["error"] == "not_found"


def test_non_loopback_bind_requires_explicit_opt_in() -> None:
    validate_bind_host("127.0.0.1", allow_remote=False)
    validate_bind_host("::1", allow_remote=False)
    validate_bind_host("localhost", allow_remote=False)

    with pytest.raises(LocalConsoleConfigurationError, match="non-loopback"):
        validate_bind_host("0.0.0.0", allow_remote=False)

    validate_bind_host("0.0.0.0", allow_remote=True)


def test_refresh_interval_is_bounded() -> None:
    with pytest.raises(LocalConsoleConfigurationError, match="refresh_seconds"):
        LocalConsoleConfig(
            sources=DataHealthSourcePaths(
                tiingo_acceptance_path=Path("tiingo.json"),
                free_stack_acceptance_path=Path("free.json"),
            ),
            refresh_seconds=1,
        )
