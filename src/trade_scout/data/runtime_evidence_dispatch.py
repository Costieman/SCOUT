"""Runtime-evidence dispatch for provider-specific evidence schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trade_scout.data.acceptance import (
    AcceptanceEvidence,
    AcceptanceEvidenceStatus,
    DataFoundationCriterion,
)
from trade_scout.data.evidence_bridge import (
    RuntimeEvidenceAssessment,
    RuntimeEvidenceError,
)
from trade_scout.data.evidence_bridge import (
    assess_runtime_evidence as assess_generic_runtime_evidence,
)

_EODHD_DAILY_UPDATE_SCHEMA = "eodhd-daily-update-evidence-v0.1"


def assess_runtime_evidence(path: Path) -> RuntimeEvidenceAssessment:
    """Assess provider-specific schemas before delegating to the generic evidence bridge."""

    payload = _read_json(path)
    if payload.get("schema_version") == _EODHD_DAILY_UPDATE_SCHEMA:
        return _assess_eodhd_daily_update(path, payload)
    return assess_generic_runtime_evidence(path)


def _assess_eodhd_daily_update(
    path: Path,
    payload: dict[str, Any],
) -> RuntimeEvidenceAssessment:
    if payload.get("provider_id") != "eodhd":
        raise RuntimeEvidenceError("EODHD daily-update evidence requires provider_id='eodhd'")

    parent = _required_text(payload, "parent_dataset_version")
    target = _required_text(payload, "target_dataset_version")
    if parent == target:
        raise RuntimeEvidenceError("daily-update parent and target dataset versions must differ")
    _required_text(payload, "correction_window_start")

    incoming = _required_nonnegative_int(payload, "incoming_count")
    added = _required_nonnegative_int(payload, "added_count")
    revised = _required_nonnegative_int(payload, "revised_count")
    unchanged = _required_nonnegative_int(payload, "unchanged_incoming_count")
    _required_nonnegative_int(payload, "carried_forward_count")
    change_count = _required_nonnegative_int(payload, "change_count")

    if incoming != added + revised + unchanged:
        raise RuntimeEvidenceError(
            "daily-update incoming_count must equal added + revised + unchanged overlap"
        )
    if change_count != added + revised:
        raise RuntimeEvidenceError("daily-update change_count contradicts added/revised counts")
    if payload.get("requires_new_version") is not (change_count > 0):
        raise RuntimeEvidenceError("daily-update requires_new_version contradicts change_count")
    if incoming < 1:
        raise RuntimeEvidenceError(
            "daily-update evidence requires at least one incoming observation"
        )

    live = payload.get("live_provider_observation") is True
    overlap_count = revised + unchanged
    demonstrated = live and overlap_count > 0
    status = (
        AcceptanceEvidenceStatus.DEMONSTRATED if demonstrated else AcceptanceEvidenceStatus.PARTIAL
    )
    if not live:
        note = (
            "EODHD revision mechanics were measured, but the incoming observations were not "
            "identified as a live-provider retrieval."
        )
    elif overlap_count == 0:
        note = (
            "Live EODHD observations were measured, but the run contained no correction-lookback "
            "overlap and therefore does not demonstrate deterministic overlap handling."
        )
    else:
        note = (
            "Live EODHD correction-lookback evidence includes deterministic overlap handling, "
            f"with {added} appended, {revised} revised, and {unchanged} unchanged observations."
        )

    return RuntimeEvidenceAssessment(
        source_path=path,
        evidence=AcceptanceEvidence(
            criterion=DataFoundationCriterion.INCREMENTAL_UPDATE,
            status=status,
            evidence=(str(path),),
            note=note,
        ),
    )


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeEvidenceError(f"daily-update {field} must be non-empty text")
    return value.strip()


def _required_nonnegative_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeEvidenceError(f"daily-update {field} must be a non-negative integer")
    return value


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
