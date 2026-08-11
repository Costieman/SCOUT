"""Metadata-only review probe for acquired Tiingo symbols awaiting identity review.

The probe reads the derived durable profile and reviewed identity candidate. It never reads
provider payload values and never promotes identity or prices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotCandidate,
    load_reviewed_identity_snapshot_candidate,
)

_STRUCTURAL_COUNT_FIELDS = (
    "invalid_date_row_count",
    "duplicate_date_count",
    "non_monotonic_date_count",
    "missing_required_field_row_count",
    "invalid_numeric_row_count",
    "ohlc_invariant_violation_count",
    "negative_volume_count",
    "long_calendar_gap_count",
)


class TiingoReviewProbeError(RuntimeError):
    """Raised when metadata required for a safe identity review probe is malformed."""


@dataclass(frozen=True, slots=True)
class TiingoReviewProbeRow:
    """Non-price profile evidence for one acquired target awaiting identity review."""

    source_symbol: str
    row_count: int
    first_date: str
    last_date: str
    split_event_count: int
    dividend_event_count: int
    structural_anomaly_count: int


def build_tiingo_review_probe(
    *,
    profile_path: Path,
    candidate_path: Path,
    target_symbols: set[str],
    acquired_symbols: set[str],
) -> tuple[TiingoReviewProbeRow, ...]:
    """Return acquired target symbols not yet fully covered by reviewed identity evidence."""

    profile_by_symbol = _load_profile_symbols(profile_path)
    candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
    reviewed = _fully_reviewed_query_symbols(candidate)
    pending = sorted((target_symbols & acquired_symbols) - reviewed)

    missing_profile = sorted(set(pending) - set(profile_by_symbol))
    if missing_profile:
        raise TiingoReviewProbeError(
            f"acquired review targets are missing from the durable profile: {missing_profile}"
        )

    rows = []
    for symbol in pending:
        item = profile_by_symbol[symbol]
        first_date = _required_text(item.get("first_date"), f"{symbol}.first_date")
        last_date = _required_text(item.get("last_date"), f"{symbol}.last_date")
        structural_anomaly_count = sum(
            _non_negative_int(item.get(field), f"{symbol}.{field}")
            for field in _STRUCTURAL_COUNT_FIELDS
        )
        rows.append(
            TiingoReviewProbeRow(
                source_symbol=symbol,
                row_count=_positive_int(item.get("row_count"), f"{symbol}.row_count"),
                first_date=first_date,
                last_date=last_date,
                split_event_count=_non_negative_int(
                    item.get("split_event_count"), f"{symbol}.split_event_count"
                ),
                dividend_event_count=_non_negative_int(
                    item.get("dividend_event_count"), f"{symbol}.dividend_event_count"
                ),
                structural_anomaly_count=structural_anomaly_count,
            )
        )
    return tuple(rows)


def _fully_reviewed_query_symbols(candidate: ReviewedIdentitySnapshotCandidate) -> set[str]:
    blocked = {gap.instrument_id for gap in candidate.coverage_gaps}
    return {
        link.query_symbol
        for link in candidate.provider_series_links
        if link.provider_id == "tiingo" and link.instrument_id not in blocked
    }


def _load_profile_symbols(path: Path) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoReviewProbeError(f"cannot read Tiingo profile: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoReviewProbeError("Tiingo profile is invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "tiingo-durable-profile-v0.1"
    ):
        raise TiingoReviewProbeError("unsupported Tiingo durable profile")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list):
        raise TiingoReviewProbeError("Tiingo profile symbols must be an array")

    indexed: dict[str, dict[str, object]] = {}
    for raw in raw_symbols:
        if not isinstance(raw, dict):
            raise TiingoReviewProbeError("Tiingo profile symbol entry must be an object")
        symbol = _required_text(raw.get("source_symbol"), "source_symbol").upper()
        if symbol in indexed:
            raise TiingoReviewProbeError(f"duplicate Tiingo profile symbol: {symbol}")
        indexed[symbol] = raw
    return indexed


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TiingoReviewProbeError(f"{field} must be non-empty text")
    return value.strip()


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TiingoReviewProbeError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _non_negative_int(value, field)
    if result < 1:
        raise TiingoReviewProbeError(f"{field} must be positive")
    return result


__all__ = ["TiingoReviewProbeError", "TiingoReviewProbeRow", "build_tiingo_review_probe"]
