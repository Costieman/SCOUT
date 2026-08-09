"""Conservative bridge from runtime evidence reports to Phase 1 acceptance evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trade_scout.data.acceptance import (
    AcceptanceEvidence,
    AcceptanceEvidenceStatus,
    DataFoundationCriterion,
)


class RuntimeEvidenceError(ValueError):
    """Raised when runtime evidence is malformed or cannot support the claimed criterion."""


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceAssessment:
    """One validated runtime artifact and the acceptance evidence it can support."""

    source_path: Path
    evidence: AcceptanceEvidence


def assess_runtime_evidence(path: Path) -> RuntimeEvidenceAssessment:
    """Validate one known runtime report and derive evidence without optimistic inference."""

    payload = _read_json(path)
    evaluation_id = payload.get("evaluation_id")
    if evaluation_id == "alpha-vantage-live-evaluation-v0.3":
        return _assess_listing_evaluation(path, payload)
    if evaluation_id == "alpha-tiingo-cross-validation-v0.1":
        return _assess_cross_provider_validation(path, payload)
    if _looks_like_storage_benchmark(payload):
        return _assess_storage_benchmark(path, payload)
    if "cases" in payload and payload.get("provider_id"):
        return _assess_historical_ohlcv(path, payload)
    raise RuntimeEvidenceError(f"unsupported runtime evidence report: {path}")


def _assess_listing_evaluation(path: Path, payload: dict[str, Any]) -> RuntimeEvidenceAssessment:
    progress = payload.get("progress")
    snapshots = payload.get("listing_snapshots")
    if not isinstance(progress, dict) or not isinstance(snapshots, list):
        raise RuntimeEvidenceError("listing evaluation report is missing progress/snapshots")
    complete = progress.get("complete") is True
    has_historical_delisted = any(
        isinstance(item, dict)
        and item.get("as_of") != "latest"
        and isinstance(item.get("delisted_count"), int)
        and item["delisted_count"] > 0
        for item in snapshots
    )
    status = (
        AcceptanceEvidenceStatus.DEMONSTRATED
        if complete and has_historical_delisted
        else AcceptanceEvidenceStatus.PARTIAL
    )
    note = (
        "Completed listing evaluation contains historical delisted securities."
        if status is AcceptanceEvidenceStatus.DEMONSTRATED
        else "Listing evidence is incomplete or lacks demonstrated historical delisted coverage."
    )
    return RuntimeEvidenceAssessment(
        source_path=path,
        evidence=AcceptanceEvidence(
            criterion=DataFoundationCriterion.DELISTINGS,
            status=status,
            evidence=(str(path),),
            note=note,
        ),
    )


def _assess_historical_ohlcv(path: Path, payload: dict[str, Any]) -> RuntimeEvidenceAssessment:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RuntimeEvidenceError("historical OHLCV report requires non-empty cases")
    passed = payload.get("passed") is True
    all_cases_have_dates = all(
        isinstance(case, dict)
        and case.get("first_trade_date") is not None
        and case.get("last_trade_date") is not None
        and isinstance(case.get("observation_count"), int)
        and case["observation_count"] > 0
        for case in cases
    )
    status = (
        AcceptanceEvidenceStatus.DEMONSTRATED
        if passed and all_cases_have_dates
        else AcceptanceEvidenceStatus.PARTIAL
    )
    note = (
        "Configured historical OHLCV cases passed repeatability, scope, uniqueness, ordering, "
        "and coverage checks."
        if status is AcceptanceEvidenceStatus.DEMONSTRATED
        else "Historical OHLCV runtime evidence is incomplete or contains failed configured checks."
    )
    return RuntimeEvidenceAssessment(
        source_path=path,
        evidence=AcceptanceEvidence(
            criterion=DataFoundationCriterion.HISTORICAL_INGESTION,
            status=status,
            evidence=(str(path),),
            note=note,
        ),
    )


def _assess_cross_provider_validation(
    path: Path,
    payload: dict[str, Any],
) -> RuntimeEvidenceAssessment:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise RuntimeEvidenceError("cross-provider report cases must be a list")
    expected_count = payload.get("expected_case_count")
    completed_count = payload.get("completed_case_count")
    unresolved_count = payload.get("unresolved_discrepancy_count")
    if not all(isinstance(value, int) for value in (expected_count, completed_count, unresolved_count)):
        raise RuntimeEvidenceError("cross-provider report counts must be integers")
    if expected_count < 1 or completed_count < 0 or completed_count > expected_count:
        raise RuntimeEvidenceError("cross-provider report contains invalid case counts")
    if unresolved_count < 0:
        raise RuntimeEvidenceError("cross-provider unresolved count must be non-negative")

    complete = payload.get("complete") is True and completed_count == expected_count
    representative_accepted = payload.get("representative_sample_accepted") is True
    no_unresolved = unresolved_count == 0
    status = (
        AcceptanceEvidenceStatus.DEMONSTRATED
        if complete and representative_accepted and no_unresolved
        else AcceptanceEvidenceStatus.PARTIAL
    )
    if not complete:
        note = "Cross-provider evidence is incomplete; not all configured cases finished."
    elif not no_unresolved:
        note = "Cross-provider evidence contains unresolved provider discrepancies requiring review."
    elif not representative_accepted:
        note = (
            "Cross-provider cases completed without unresolved discrepancies, but representative "
            "sample acceptance has not been explicitly reviewed."
        )
    else:
        note = (
            "Representative cross-provider validation completed with no unresolved discrepancies."
        )
    return RuntimeEvidenceAssessment(
        source_path=path,
        evidence=AcceptanceEvidence(
            criterion=DataFoundationCriterion.CROSS_PROVIDER_VALIDATION,
            status=status,
            evidence=(str(path),),
            note=note,
        ),
    )


def _looks_like_storage_benchmark(payload: dict[str, Any]) -> bool:
    required = {
        "dataset_version",
        "record_count",
        "unique_instrument_count",
        "first_trade_date",
        "last_trade_date",
        "parquet_bytes",
        "filtered_query_count",
        "representative_sample_accepted",
    }
    return required <= set(payload)


def _assess_storage_benchmark(path: Path, payload: dict[str, Any]) -> RuntimeEvidenceAssessment:
    numeric_fields = (
        "record_count",
        "unique_instrument_count",
        "parquet_bytes",
        "filtered_query_count",
    )
    for field in numeric_fields:
        value = payload.get(field)
        if not isinstance(value, int) or value < 0:
            raise RuntimeEvidenceError(f"storage benchmark {field} must be a non-negative integer")
    has_sample = (
        payload["record_count"] > 0
        and payload["unique_instrument_count"] > 0
        and payload["parquet_bytes"] > 0
    )
    representative_accepted = payload.get("representative_sample_accepted") is True
    status = (
        AcceptanceEvidenceStatus.DEMONSTRATED
        if has_sample and representative_accepted
        else AcceptanceEvidenceStatus.PARTIAL
    )
    note = (
        "Representative Parquet/DuckDB sample was explicitly accepted and benchmarked."
        if status is AcceptanceEvidenceStatus.DEMONSTRATED
        else "Storage measurements exist, but representative-sample acceptance remains outstanding."
    )
    return RuntimeEvidenceAssessment(
        source_path=path,
        evidence=AcceptanceEvidence(
            criterion=DataFoundationCriterion.STORAGE_BENCHMARK,
            status=status,
            evidence=(str(path),),
            note=note,
        ),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeEvidenceError(f"cannot read runtime evidence: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeEvidenceError(f"runtime evidence is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeEvidenceError("runtime evidence root must be a JSON object")
    return payload
