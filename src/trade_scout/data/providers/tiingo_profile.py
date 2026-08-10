"""Derived quality profiling for checksum-verified durable Tiingo history.

This module reads private raw Tiingo payloads only after their durable receipts verify. It emits
summary diagnostics and provenance identifiers, never raw OHLCV values or credentials.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trade_scout.data.durable_raw_receipt import (
    load_durable_raw_receipt,
    verify_durable_raw_receipt,
)

_REQUIRED_FIELDS = frozenset(
    {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjOpen",
        "adjHigh",
        "adjLow",
        "adjClose",
        "divCash",
        "splitFactor",
    }
)
_NUMERIC_FIELDS = frozenset(_REQUIRED_FIELDS - {"date"})


class TiingoProfileError(RuntimeError):
    """Raised when durable Tiingo evidence cannot be safely profiled."""


@dataclass(frozen=True, slots=True)
class TiingoSymbolProfile:
    """Non-price diagnostics for one durable Tiingo acquisition subject."""

    source_symbol: str
    receipt_id: str
    payload_checksum_sha256: str
    row_count: int
    first_date: str | None
    last_date: str | None
    invalid_date_row_count: int
    duplicate_date_count: int
    non_monotonic_date_count: int
    missing_required_field_row_count: int
    invalid_numeric_row_count: int
    ohlc_invariant_violation_count: int
    negative_volume_count: int
    split_event_count: int
    dividend_event_count: int
    long_calendar_gap_count: int


@dataclass(frozen=True, slots=True)
class TiingoDurableProfile:
    """Workspace-safe aggregate report over verified private Tiingo payloads."""

    schema_version: str
    generated_at: datetime
    storage_namespace: str
    receipt_count: int
    symbol_count: int
    total_row_count: int
    invalid_date_row_count: int
    duplicate_date_count: int
    non_monotonic_date_count: int
    missing_required_field_row_count: int
    invalid_numeric_row_count: int
    ohlc_invariant_violation_count: int
    negative_volume_count: int
    split_event_count: int
    dividend_event_count: int
    long_calendar_gap_count: int
    symbols: tuple[TiingoSymbolProfile, ...]


def profile_durable_tiingo(
    *,
    receipt_root: Path,
    raw_root: Path,
    storage_namespace: str,
    generated_at: datetime | None = None,
) -> TiingoDurableProfile:
    """Profile every verified Tiingo receipt under one private workspace."""

    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")

    receipt_paths = tuple(sorted(receipt_root.rglob("*.json"))) if receipt_root.exists() else ()
    seen_subjects: set[str] = set()
    profiles: list[TiingoSymbolProfile] = []

    for receipt_path in receipt_paths:
        receipt = load_durable_raw_receipt(receipt_path)
        if receipt.provider_id != "tiingo":
            raise TiingoProfileError(f"non-Tiingo receipt found under Tiingo root: {receipt_path}")
        if receipt.subject_key in seen_subjects:
            raise TiingoProfileError(
                f"multiple durable receipts found for source symbol {receipt.subject_key}; "
                "profiling requires one authoritative full-history receipt per symbol"
            )
        seen_subjects.add(receipt.subject_key)
        record = verify_durable_raw_receipt(
            receipt,
            durable_root=raw_root,
            storage_namespace=storage_namespace,
        )
        try:
            raw: object = json.loads(record.payload_path.read_bytes())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TiingoProfileError(
                f"verified Tiingo payload is not readable JSON for {receipt.subject_key}"
            ) from exc
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise TiingoProfileError(
                f"verified Tiingo payload has unexpected response shape for {receipt.subject_key}"
            )
        profiles.append(
            _profile_symbol(
                receipt.subject_key,
                receipt.receipt_id,
                receipt.payload_checksum_sha256,
                raw,
            )
        )

    return TiingoDurableProfile(
        schema_version="tiingo-durable-profile-v0.1",
        generated_at=timestamp,
        storage_namespace=storage_namespace,
        receipt_count=len(receipt_paths),
        symbol_count=len(profiles),
        total_row_count=sum(item.row_count for item in profiles),
        invalid_date_row_count=sum(item.invalid_date_row_count for item in profiles),
        duplicate_date_count=sum(item.duplicate_date_count for item in profiles),
        non_monotonic_date_count=sum(item.non_monotonic_date_count for item in profiles),
        missing_required_field_row_count=sum(
            item.missing_required_field_row_count for item in profiles
        ),
        invalid_numeric_row_count=sum(item.invalid_numeric_row_count for item in profiles),
        ohlc_invariant_violation_count=sum(
            item.ohlc_invariant_violation_count for item in profiles
        ),
        negative_volume_count=sum(item.negative_volume_count for item in profiles),
        split_event_count=sum(item.split_event_count for item in profiles),
        dividend_event_count=sum(item.dividend_event_count for item in profiles),
        long_calendar_gap_count=sum(item.long_calendar_gap_count for item in profiles),
        symbols=tuple(sorted(profiles, key=lambda item: item.source_symbol)),
    )


def persist_tiingo_durable_profile(path: Path, profile: TiingoDurableProfile) -> None:
    """Persist derived diagnostics atomically without raw provider values."""

    payload = asdict(profile)
    payload["generated_at"] = profile.generated_at.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _profile_symbol(
    symbol: str,
    receipt_id: str,
    payload_checksum_sha256: str,
    rows: list[dict[str, Any]],
) -> TiingoSymbolProfile:
    dates: list[datetime] = []
    invalid_dates = 0
    duplicate_dates = 0
    non_monotonic = 0
    missing_required = 0
    invalid_numeric = 0
    ohlc_violations = 0
    negative_volume = 0
    split_events = 0
    dividend_events = 0
    seen_dates: set[str] = set()
    previous: datetime | None = None
    long_gaps = 0

    for row in rows:
        if not _REQUIRED_FIELDS.issubset(row):
            missing_required += 1

        parsed_date = _parse_row_date(row.get("date"))
        if parsed_date is None:
            invalid_dates += 1
        else:
            date_key = parsed_date.date().isoformat()
            if date_key in seen_dates:
                duplicate_dates += 1
            seen_dates.add(date_key)
            if previous is not None:
                if parsed_date <= previous:
                    non_monotonic += 1
                if (parsed_date.date() - previous.date()).days > 7:
                    long_gaps += 1
            previous = parsed_date
            dates.append(parsed_date)

        numeric_invalid_this_row = False
        for field in _NUMERIC_FIELDS:
            if field in row and not _finite_number(row.get(field)):
                numeric_invalid_this_row = True
        if numeric_invalid_this_row:
            invalid_numeric += 1

        open_value = _as_float(row.get("open"))
        high_value = _as_float(row.get("high"))
        low_value = _as_float(row.get("low"))
        close_value = _as_float(row.get("close"))
        if None not in (open_value, high_value, low_value, close_value):
            assert open_value is not None
            assert high_value is not None
            assert low_value is not None
            assert close_value is not None
            if (
                high_value < low_value
                or high_value < open_value
                or high_value < close_value
                or low_value > open_value
                or low_value > close_value
            ):
                ohlc_violations += 1

        volume = _as_float(row.get("volume"))
        if volume is not None and volume < 0:
            negative_volume += 1
        split_factor = _as_float(row.get("splitFactor"))
        if split_factor is not None and split_factor != 1.0:
            split_events += 1
        dividend = _as_float(row.get("divCash"))
        if dividend is not None and dividend != 0.0:
            dividend_events += 1

    first = min(dates).date().isoformat() if dates else None
    last = max(dates).date().isoformat() if dates else None
    return TiingoSymbolProfile(
        source_symbol=symbol,
        receipt_id=receipt_id,
        payload_checksum_sha256=payload_checksum_sha256,
        row_count=len(rows),
        first_date=first,
        last_date=last,
        invalid_date_row_count=invalid_dates,
        duplicate_date_count=duplicate_dates,
        non_monotonic_date_count=non_monotonic,
        missing_required_field_row_count=missing_required,
        invalid_numeric_row_count=invalid_numeric,
        ohlc_invariant_violation_count=ohlc_violations,
        negative_volume_count=negative_volume,
        split_event_count=split_events,
        dividend_event_count=dividend_events,
        long_calendar_gap_count=long_gaps,
    )


def _parse_row_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _finite_number(value: object) -> bool:
    return _as_float(value) is not None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None
