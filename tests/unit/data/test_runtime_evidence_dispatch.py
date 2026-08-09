import json

import pytest

from trade_scout.data.acceptance import AcceptanceEvidenceStatus, DataFoundationCriterion
from trade_scout.data.evidence_bridge import RuntimeEvidenceError
from trade_scout.data.runtime_evidence_dispatch import assess_runtime_evidence


def _write(tmp_path, **overrides):
    payload = {
        "schema_version": "eodhd-daily-update-evidence-v0.1",
        "provider_id": "eodhd",
        "live_provider_observation": True,
        "parent_dataset_version": "v1",
        "target_dataset_version": "v2",
        "correction_window_start": "2026-08-01",
        "incoming_count": 3,
        "added_count": 1,
        "revised_count": 1,
        "unchanged_incoming_count": 1,
        "carried_forward_count": 100,
        "requires_new_version": True,
        "change_count": 2,
    }
    payload.update(overrides)
    path = tmp_path / "eodhd-update.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_live_overlap_can_demonstrate_incremental_update(tmp_path) -> None:
    assessment = assess_runtime_evidence(_write(tmp_path))

    assert assessment.evidence.criterion is DataFoundationCriterion.INCREMENTAL_UPDATE
    assert assessment.evidence.status is AcceptanceEvidenceStatus.DEMONSTRATED


def test_synthetic_or_append_only_evidence_remains_partial(tmp_path) -> None:
    synthetic = assess_runtime_evidence(_write(tmp_path, live_provider_observation=False))
    assert synthetic.evidence.status is AcceptanceEvidenceStatus.PARTIAL

    append_only = assess_runtime_evidence(
        _write(
            tmp_path,
            incoming_count=2,
            added_count=2,
            revised_count=0,
            unchanged_incoming_count=0,
            change_count=2,
        )
    )
    assert append_only.evidence.status is AcceptanceEvidenceStatus.PARTIAL


def test_contradictory_update_counts_fail_closed(tmp_path) -> None:
    with pytest.raises(RuntimeEvidenceError, match="incoming_count"):
        assess_runtime_evidence(_write(tmp_path, incoming_count=4))

    with pytest.raises(RuntimeEvidenceError, match="requires_new_version"):
        assess_runtime_evidence(_write(tmp_path, requires_new_version=False))

    with pytest.raises(RuntimeEvidenceError, match="parent and target"):
        assess_runtime_evidence(_write(tmp_path, target_dataset_version="v1"))
