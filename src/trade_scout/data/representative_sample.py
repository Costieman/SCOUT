"""Explicit representativeness gate for Phase 1 storage-benchmark evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DailyBar, InstrumentRecord, SecurityType


class RepresentativeSampleError(ValueError):
    """Raised when a representativeness policy or supplied sample is malformed."""


@dataclass(frozen=True, slots=True)
class RepresentativeSamplePolicy:
    """Versioned minimum scope required before a benchmark sample may be called representative."""

    version: str
    min_record_count: int
    min_unique_instruments: int
    min_span_days: int
    min_delisted_instruments: int
    min_exchanges: int
    require_common_stock: bool = True

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise RepresentativeSampleError(
                "representative-sample policy version must be non-empty"
            )
        for name, value in (
            ("min_record_count", self.min_record_count),
            ("min_unique_instruments", self.min_unique_instruments),
            ("min_span_days", self.min_span_days),
            ("min_delisted_instruments", self.min_delisted_instruments),
            ("min_exchanges", self.min_exchanges),
        ):
            if value < 0:
                raise RepresentativeSampleError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class RepresentativeSampleAssessment:
    """Measured sample scope plus explicit failed representativeness conditions."""

    policy_version: str
    record_count: int
    unique_instrument_count: int
    first_trade_date: date
    last_trade_date: date
    span_days: int
    delisted_instrument_count: int
    exchange_count: int
    common_stock_count: int
    failures: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.failures


def load_representative_sample_policy(path: Path) -> RepresentativeSamplePolicy:
    """Load a strict JSON policy without inventing defaults for missing scope requirements."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RepresentativeSampleError(
            f"cannot read representative-sample policy: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RepresentativeSampleError(
            f"representative-sample policy is invalid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise RepresentativeSampleError("representative-sample policy root must be a JSON object")

    required = {
        "version",
        "min_record_count",
        "min_unique_instruments",
        "min_span_days",
        "min_delisted_instruments",
        "min_exchanges",
        "require_common_stock",
    }
    missing = required - set(payload)
    unknown = set(payload) - required
    if missing or unknown:
        details = []
        if missing:
            details.append("missing=" + ",".join(sorted(missing)))
        if unknown:
            details.append("unknown=" + ",".join(sorted(unknown)))
        raise RepresentativeSampleError(
            "invalid representative-sample policy fields: " + "; ".join(details)
        )

    def _nonnegative_int(name: str) -> int:
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RepresentativeSampleError(f"{name} must be a non-negative integer")
        return int(value)

    version = payload["version"]
    require_common_stock = payload["require_common_stock"]
    if not isinstance(version, str) or not version.strip():
        raise RepresentativeSampleError("version must be non-empty text")
    if not isinstance(require_common_stock, bool):
        raise RepresentativeSampleError("require_common_stock must be boolean")

    return RepresentativeSamplePolicy(
        version=version,
        min_record_count=_nonnegative_int("min_record_count"),
        min_unique_instruments=_nonnegative_int("min_unique_instruments"),
        min_span_days=_nonnegative_int("min_span_days"),
        min_delisted_instruments=_nonnegative_int("min_delisted_instruments"),
        min_exchanges=_nonnegative_int("min_exchanges"),
        require_common_stock=require_common_stock,
    )


def assess_representative_sample(
    bars: tuple[DailyBar, ...],
    instruments: tuple[InstrumentRecord, ...],
    *,
    policy: RepresentativeSamplePolicy,
) -> RepresentativeSampleAssessment:
    """Assess observable benchmark scope without overstating statistical representativeness."""

    if not bars:
        raise RepresentativeSampleError("representative sample requires canonical bars")
    if not instruments:
        raise RepresentativeSampleError("representative sample requires instrument-master records")

    instrument_by_id = {instrument.instrument_id: instrument for instrument in instruments}
    if len(instrument_by_id) != len(instruments):
        raise RepresentativeSampleError("instrument master contains duplicate instrument IDs")

    bar_ids = {bar.instrument_id for bar in bars}
    unknown = bar_ids - set(instrument_by_id)
    if unknown:
        details = ",".join(sorted(str(item) for item in unknown))
        raise RepresentativeSampleError(f"canonical bars reference unknown instruments: {details}")

    dates = tuple(bar.trade_date for bar in bars)
    first_trade_date = min(dates)
    last_trade_date = max(dates)
    span_days = (last_trade_date - first_trade_date).days
    sample_instruments = tuple(instrument_by_id[item] for item in sorted(bar_ids, key=str))
    delisted_count = sum(instrument.delisting_date is not None for instrument in sample_instruments)
    exchanges = {instrument.exchange for instrument in sample_instruments}
    common_stock_count = sum(
        instrument.security_type is SecurityType.COMMON_STOCK for instrument in sample_instruments
    )

    failures: list[str] = []
    if len(bars) < policy.min_record_count:
        failures.append("record_count_below_minimum")
    if len(sample_instruments) < policy.min_unique_instruments:
        failures.append("unique_instrument_count_below_minimum")
    if span_days < policy.min_span_days:
        failures.append("date_span_below_minimum")
    if delisted_count < policy.min_delisted_instruments:
        failures.append("delisted_instrument_count_below_minimum")
    if len(exchanges) < policy.min_exchanges:
        failures.append("exchange_count_below_minimum")
    if policy.require_common_stock and common_stock_count == 0:
        failures.append("common_stock_absent")

    return RepresentativeSampleAssessment(
        policy_version=policy.version,
        record_count=len(bars),
        unique_instrument_count=len(sample_instruments),
        first_trade_date=first_trade_date,
        last_trade_date=last_trade_date,
        span_days=span_days,
        delisted_instrument_count=delisted_count,
        exchange_count=len(exchanges),
        common_stock_count=common_stock_count,
        failures=tuple(failures),
    )
