"""Build a fail-closed queue containing only unresolved, not-yet-reviewed Tiingo symbols."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate


class RemainingIdentityQueueError(RuntimeError):
    """Raised when unresolved evidence cannot be reconciled with the locked reviewed set."""


@dataclass(frozen=True, slots=True)
class RemainingIdentityQueueSummary:
    reviewed_symbol_count: int
    source_remaining_count: int
    queued_symbol_count: int
    locked_overlap_count: int
    reason_counts: dict[str, int]
    queued_symbols: tuple[str, ...]


def build_remaining_identity_queue(
    *, reviewed_candidate_path: Path, extended_remaining_path: Path
) -> RemainingIdentityQueueSummary:
    """Return unresolved symbols after excluding every already-reviewed Tiingo symbol.

    The reviewed candidate is authoritative for the locked set. A symbol already present there is
    never eligible for another resolver pass. Any overlap in the remaining evidence is counted and
    excluded rather than reprocessed.
    """

    candidate = load_reviewed_identity_snapshot_candidate(reviewed_candidate_path)
    locked = {
        link.query_symbol.strip().upper()
        for link in candidate.provider_series_links
        if link.provider_id == "tiingo"
    }
    payload = _load_object(extended_remaining_path)
    rows = payload.get("resolutions")
    if not isinstance(rows, list):
        raise RemainingIdentityQueueError("extended remaining evidence must contain resolutions")

    queued: dict[str, dict[str, object]] = {}
    overlap = 0
    reasons: Counter[str] = Counter()
    for raw in rows:
        if not isinstance(raw, dict):
            raise RemainingIdentityQueueError("extended remaining evidence contains malformed row")
        symbol = _text(raw.get("source_symbol"), "source_symbol").upper()
        if symbol in locked:
            overlap += 1
            continue
        if symbol in queued:
            raise RemainingIdentityQueueError(f"duplicate unresolved symbol {symbol}")
        reason = _text(raw.get("resolution_kind"), "resolution_kind")
        queued[symbol] = raw
        reasons[reason] += 1

    return RemainingIdentityQueueSummary(
        reviewed_symbol_count=len(locked),
        source_remaining_count=len(rows),
        queued_symbol_count=len(queued),
        locked_overlap_count=overlap,
        reason_counts=dict(sorted(reasons.items())),
        queued_symbols=tuple(sorted(queued)),
    )


def persist_remaining_identity_queue(path: Path, summary: RemainingIdentityQueueSummary) -> None:
    payload = {
        "schema_version": "tiingo-remaining-identity-queue-v0.1",
        "reviewed_symbol_count": summary.reviewed_symbol_count,
        "source_remaining_count": summary.source_remaining_count,
        "queued_symbol_count": summary.queued_symbol_count,
        "locked_overlap_count": summary.locked_overlap_count,
        "reason_counts": summary.reason_counts,
        "symbols": list(summary.queued_symbols),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RemainingIdentityQueueError(f"required remaining evidence is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RemainingIdentityQueueError("remaining evidence root must be an object")
    return payload


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RemainingIdentityQueueError(f"{field} must be non-empty text")
    return value.strip()


__all__ = [
    "RemainingIdentityQueueError",
    "RemainingIdentityQueueSummary",
    "build_remaining_identity_queue",
    "persist_remaining_identity_queue",
]
