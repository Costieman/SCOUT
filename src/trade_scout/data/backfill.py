"""Deterministic historical daily-bar backfill planning, checkpointing, and staging."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest, ProviderAdapter, ProviderDailyBar


class BackfillPlanError(ValueError):
    """Raised when a backfill plan is invalid or internally inconsistent."""


class BackfillRuntimeConflictError(RuntimeError):
    """Raised when immutable staged/checkpoint state conflicts with a requested backfill."""


class BackfillExecutionError(RuntimeError):
    """Raised when one deterministic backfill batch cannot be completed."""

    def __init__(self, batch_id: str, message: str) -> None:
        super().__init__(f"backfill batch {batch_id} failed: {message}")
        self.batch_id = batch_id


@dataclass(frozen=True, slots=True)
class BackfillBatch:
    """One bounded provider-neutral daily-bar request in a historical backfill plan."""

    batch_id: str
    start: date
    end: date
    provider_symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    """Immutable deterministic specification for a bounded historical backfill."""

    plan_id: str
    provider_id: str
    start: date
    end: date
    provider_symbols: tuple[str, ...]
    adjustment: PriceRepresentation
    max_calendar_days_per_batch: int
    max_symbols_per_batch: int
    batches: tuple[BackfillBatch, ...]


@dataclass(frozen=True, slots=True)
class BackfillCheckpoint:
    """Durable progress marker advanced only after a staged batch is persisted."""

    plan_id: str
    completed_batch_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BackfillExecutionResult:
    """Completed staged backfill suitable for downstream normalization/quality gates."""

    plan_id: str
    batch_count: int
    record_count: int
    bars: tuple[ProviderDailyBar, ...]


def plan_daily_bar_backfill(
    *,
    provider_id: str,
    provider_symbols: Sequence[str],
    start: date,
    end: date,
    max_calendar_days_per_batch: int,
    max_symbols_per_batch: int,
    adjustment: PriceRepresentation = PriceRepresentation.RAW,
) -> BackfillPlan:
    """Build deterministic date/symbol batches without embedding provider-specific limits."""

    if not provider_id.strip():
        raise BackfillPlanError("provider_id must be non-empty")
    if end < start:
        raise BackfillPlanError("backfill end must be on or after start")
    if max_calendar_days_per_batch < 1:
        raise BackfillPlanError("max_calendar_days_per_batch must be positive")
    if max_symbols_per_batch < 1:
        raise BackfillPlanError("max_symbols_per_batch must be positive")

    symbols = tuple(sorted(set(provider_symbols)))
    if not symbols or any(not symbol.strip() for symbol in symbols):
        raise BackfillPlanError("provider_symbols must contain non-empty symbols")
    if len(symbols) != len(provider_symbols):
        raise BackfillPlanError("provider_symbols must not contain duplicates")

    plan_spec = {
        "provider_id": provider_id,
        "provider_symbols": symbols,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "max_calendar_days_per_batch": max_calendar_days_per_batch,
        "max_symbols_per_batch": max_symbols_per_batch,
        "adjustment": str(adjustment),
    }
    plan_id = "backfill-" + _sha256_json(plan_spec)[:24]

    batches: list[BackfillBatch] = []
    sequence = 0
    for window_start, window_end in _date_windows(start, end, max_calendar_days_per_batch):
        for symbol_chunk in _chunks(symbols, max_symbols_per_batch):
            sequence += 1
            batch_spec = {
                "plan_id": plan_id,
                "sequence": sequence,
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
                "provider_symbols": symbol_chunk,
            }
            batch_id = f"batch-{sequence:06d}-{_sha256_json(batch_spec)[:12]}"
            batches.append(
                BackfillBatch(
                    batch_id=batch_id,
                    start=window_start,
                    end=window_end,
                    provider_symbols=symbol_chunk,
                )
            )

    return BackfillPlan(
        plan_id=plan_id,
        provider_id=provider_id,
        start=start,
        end=end,
        provider_symbols=symbols,
        adjustment=adjustment,
        max_calendar_days_per_batch=max_calendar_days_per_batch,
        max_symbols_per_batch=max_symbols_per_batch,
        batches=tuple(batches),
    )


class BackfillRuntimeStore:
    """Immutable provider-neutral staged batches plus atomic progress checkpoints."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def checkpoint(self, plan: BackfillPlan) -> BackfillCheckpoint:
        """Read or initialize the durable checkpoint for one exact plan."""

        plan_root = self._plan_root(plan.plan_id)
        plan_root.mkdir(parents=True, exist_ok=True)
        self._persist_plan(plan)
        path = plan_root / "checkpoint.json"
        if not path.exists():
            checkpoint = BackfillCheckpoint(plan_id=plan.plan_id, completed_batch_ids=())
            self._write_json_atomic(path, _checkpoint_payload(checkpoint))
            return checkpoint
        return self._read_checkpoint(path, plan)

    def persist_batch(
        self,
        plan: BackfillPlan,
        batch: BackfillBatch,
        bars: Sequence[ProviderDailyBar],
    ) -> None:
        """Persist a normalized provider batch idempotently; conflicting rewrites fail."""

        self._require_plan_batch(plan, batch)
        path = self._batch_path(plan.plan_id, batch.batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plan_id": plan.plan_id,
            "batch_id": batch.batch_id,
            "bars": [_bar_payload(bar) for bar in bars],
        }
        encoded = _json_bytes(payload)
        if path.exists():
            if path.read_bytes() != encoded:
                raise BackfillRuntimeConflictError(
                    f"staged batch {batch.batch_id} already exists with different content"
                )
            return
        path.write_bytes(encoded)

    def mark_completed(self, plan: BackfillPlan, batch: BackfillBatch) -> BackfillCheckpoint:
        """Atomically advance progress after staged data are durable."""

        self._require_plan_batch(plan, batch)
        if not self._batch_path(plan.plan_id, batch.batch_id).is_file():
            raise BackfillRuntimeConflictError(
                f"cannot complete batch {batch.batch_id} before staged data are persisted"
            )
        current = self.checkpoint(plan)
        completed = set(current.completed_batch_ids)
        completed.add(batch.batch_id)
        checkpoint = BackfillCheckpoint(
            plan_id=plan.plan_id,
            completed_batch_ids=tuple(
                item.batch_id for item in plan.batches if item.batch_id in completed
            ),
        )
        self._write_json_atomic(
            self._plan_root(plan.plan_id) / "checkpoint.json",
            _checkpoint_payload(checkpoint),
        )
        return checkpoint

    def load_batch(self, plan: BackfillPlan, batch: BackfillBatch) -> tuple[ProviderDailyBar, ...]:
        """Read one staged provider-neutral batch and validate its immutable envelope."""

        self._require_plan_batch(plan, batch)
        path = self._batch_path(plan.plan_id, batch.batch_id)
        if not path.is_file():
            raise BackfillRuntimeConflictError(f"staged batch {batch.batch_id} is missing")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("plan_id") != plan.plan_id or payload.get("batch_id") != batch.batch_id:
            raise BackfillRuntimeConflictError(f"staged batch {batch.batch_id} envelope is invalid")
        raw_bars = payload.get("bars")
        if not isinstance(raw_bars, list):
            raise BackfillRuntimeConflictError(f"staged batch {batch.batch_id} bars are invalid")
        return tuple(_bar_from_payload(item) for item in raw_bars)

    def load_all(self, plan: BackfillPlan) -> tuple[ProviderDailyBar, ...]:
        """Load a fully completed plan and reject missing/duplicate instrument-session records."""

        checkpoint = self.checkpoint(plan)
        if checkpoint.completed_batch_ids != tuple(batch.batch_id for batch in plan.batches):
            raise BackfillRuntimeConflictError("cannot load incomplete backfill plan")
        bars = tuple(bar for batch in plan.batches for bar in self.load_batch(plan, batch))
        seen: set[tuple[str, date]] = set()
        for bar in bars:
            key = (bar.provider_instrument_id, bar.trade_date)
            if key in seen:
                raise BackfillRuntimeConflictError(
                    "duplicate provider instrument/date encountered across staged batches"
                )
            seen.add(key)
        return tuple(
            sorted(
                bars,
                key=lambda item: (item.trade_date, item.provider_instrument_id, item.symbol),
            )
        )

    def _persist_plan(self, plan: BackfillPlan) -> None:
        path = self._plan_root(plan.plan_id) / "plan.json"
        payload = _plan_payload(plan)
        encoded = _json_bytes(payload)
        if path.exists():
            if path.read_bytes() != encoded:
                raise BackfillRuntimeConflictError(
                    f"backfill plan {plan.plan_id} conflicts with persisted plan state"
                )
            return
        path.write_bytes(encoded)

    def _read_checkpoint(self, path: Path, plan: BackfillPlan) -> BackfillCheckpoint:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("plan_id") != plan.plan_id:
            raise BackfillRuntimeConflictError("checkpoint belongs to a different plan")
        completed = payload.get("completed_batch_ids")
        if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
            raise BackfillRuntimeConflictError("checkpoint completed_batch_ids are invalid")
        valid_ids = {batch.batch_id for batch in plan.batches}
        if not set(completed).issubset(valid_ids):
            raise BackfillRuntimeConflictError("checkpoint references an unknown batch")
        ordered = tuple(batch.batch_id for batch in plan.batches if batch.batch_id in completed)
        return BackfillCheckpoint(plan_id=plan.plan_id, completed_batch_ids=ordered)

    def _require_plan_batch(self, plan: BackfillPlan, batch: BackfillBatch) -> None:
        if batch not in plan.batches:
            raise BackfillRuntimeConflictError(f"batch {batch.batch_id} is not part of plan")

    def _plan_root(self, plan_id: str) -> Path:
        return self.root / plan_id

    def _batch_path(self, plan_id: str, batch_id: str) -> Path:
        return self._plan_root(plan_id) / "batches" / f"{batch_id}.json"

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(_json_bytes(payload))
        temporary.replace(path)


def execute_daily_bar_backfill(
    adapter: ProviderAdapter,
    plan: BackfillPlan,
    store: BackfillRuntimeStore,
) -> BackfillExecutionResult:
    """Execute pending batches deterministically and resume from durable staged checkpoints."""

    if adapter.provider_id != plan.provider_id:
        raise BackfillPlanError(
            f"adapter provider {adapter.provider_id} does not match plan provider "
            f"{plan.provider_id}"
        )
    checkpoint = store.checkpoint(plan)
    completed = set(checkpoint.completed_batch_ids)

    for batch in plan.batches:
        if batch.batch_id in completed:
            continue
        request = DailyBarRequest(
            start=batch.start,
            end=batch.end,
            provider_symbols=batch.provider_symbols,
            adjustment=plan.adjustment,
            run_id=f"backfill:{plan.plan_id}:{batch.batch_id}",
        )
        try:
            bars = tuple(adapter.get_daily_bars(request))
            _validate_batch_response(adapter.provider_id, batch, bars)
            store.persist_batch(plan, batch, bars)
            store.mark_completed(plan, batch)
        except Exception as exc:
            if isinstance(exc, (BackfillPlanError, BackfillRuntimeConflictError)):
                raise
            raise BackfillExecutionError(batch.batch_id, str(exc)) from exc

    bars = store.load_all(plan)
    return BackfillExecutionResult(
        plan_id=plan.plan_id,
        batch_count=len(plan.batches),
        record_count=len(bars),
        bars=bars,
    )


def _validate_batch_response(
    provider_id: str,
    batch: BackfillBatch,
    bars: Iterable[ProviderDailyBar],
) -> None:
    allowed_symbols = set(batch.provider_symbols)
    seen: set[tuple[str, date]] = set()
    for bar in bars:
        if bar.provider_id != provider_id:
            raise BackfillRuntimeConflictError(
                f"batch {batch.batch_id} returned provider {bar.provider_id}; "
                f"expected {provider_id}"
            )
        if bar.symbol not in allowed_symbols:
            raise BackfillRuntimeConflictError(
                f"batch {batch.batch_id} returned unexpected symbol {bar.symbol}"
            )
        if not batch.start <= bar.trade_date <= batch.end:
            raise BackfillRuntimeConflictError(
                f"batch {batch.batch_id} returned out-of-range date {bar.trade_date}"
            )
        key = (bar.provider_instrument_id, bar.trade_date)
        if key in seen:
            raise BackfillRuntimeConflictError(
                f"batch {batch.batch_id} returned duplicate provider instrument/date"
            )
        seen.add(key)


def _date_windows(start: date, end: date, width: int) -> Iterable[tuple[date, date]]:
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=width - 1), end)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def _chunks(items: tuple[str, ...], width: int) -> Iterable[tuple[str, ...]]:
    for index in range(0, len(items), width):
        yield items[index : index + width]


def _plan_payload(plan: BackfillPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "provider_id": plan.provider_id,
        "start": plan.start.isoformat(),
        "end": plan.end.isoformat(),
        "provider_symbols": list(plan.provider_symbols),
        "adjustment": str(plan.adjustment),
        "max_calendar_days_per_batch": plan.max_calendar_days_per_batch,
        "max_symbols_per_batch": plan.max_symbols_per_batch,
        "batches": [
            {
                "batch_id": batch.batch_id,
                "start": batch.start.isoformat(),
                "end": batch.end.isoformat(),
                "provider_symbols": list(batch.provider_symbols),
            }
            for batch in plan.batches
        ],
    }


def _checkpoint_payload(checkpoint: BackfillCheckpoint) -> dict[str, Any]:
    return {
        "plan_id": checkpoint.plan_id,
        "completed_batch_ids": list(checkpoint.completed_batch_ids),
    }


def _bar_payload(bar: ProviderDailyBar) -> dict[str, Any]:
    payload = asdict(bar)
    payload["trade_date"] = bar.trade_date.isoformat()
    return payload


def _bar_from_payload(payload: object) -> ProviderDailyBar:
    if not isinstance(payload, dict):
        raise BackfillRuntimeConflictError("staged provider bar must be an object")
    try:
        return ProviderDailyBar(
            provider_id=str(payload["provider_id"]),
            provider_instrument_id=str(payload["provider_instrument_id"]),
            symbol=str(payload["symbol"]),
            trade_date=date.fromisoformat(str(payload["trade_date"])),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
            split_factor=_optional_float(payload.get("split_factor")),
            dividend_cash=_optional_float(payload.get("dividend_cash")),
            adjusted_open=_optional_float(payload.get("adjusted_open")),
            adjusted_high=_optional_float(payload.get("adjusted_high")),
            adjusted_low=_optional_float(payload.get("adjusted_low")),
            adjusted_close=_optional_float(payload.get("adjusted_close")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BackfillRuntimeConflictError("staged provider bar has invalid fields") from exc


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise BackfillRuntimeConflictError("staged numeric field is invalid")
    return float(value)


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
