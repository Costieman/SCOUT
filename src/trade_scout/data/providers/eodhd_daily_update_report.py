"""Serialize EODHD daily-update evidence into a strict runtime report."""

from __future__ import annotations

import json
from pathlib import Path

from trade_scout.data.providers.eodhd_daily_update import EodhdDailyUpdateEvidence

_SCHEMA_VERSION = "eodhd-daily-update-evidence-v0.1"


def write_eodhd_daily_update_report(
    evidence: EodhdDailyUpdateEvidence,
    *,
    path: Path,
    live_provider_observation: bool,
) -> Path:
    """Persist one deterministic daily-update evidence report.

    The serializer records whether the incoming observations were obtained from a live EODHD
    request. That flag is intentionally explicit because provider-neutral or synthetic revision
    tests cannot demonstrate the Phase 1 incremental-update criterion.
    """

    payload = {
        "schema_version": _SCHEMA_VERSION,
        "provider_id": "eodhd",
        "live_provider_observation": live_provider_observation,
        "parent_dataset_version": str(evidence.parent_dataset_version),
        "target_dataset_version": str(evidence.target_dataset_version),
        "correction_window_start": evidence.correction_window_start.isoformat(),
        "incoming_count": evidence.incoming_count,
        "added_count": evidence.added_count,
        "revised_count": evidence.revised_count,
        "unchanged_incoming_count": evidence.unchanged_incoming_count,
        "carried_forward_count": evidence.carried_forward_count,
        "requires_new_version": evidence.requires_new_version,
        "change_count": evidence.added_count + evidence.revised_count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
