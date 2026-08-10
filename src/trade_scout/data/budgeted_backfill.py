"""Quota-aware execution for deterministic provider backfill plans.

This layer intentionally limits work per invocation rather than sleeping inside a
long-running process. Durable checkpoints in ``BackfillRuntimeStore`` make repeated
invocations resume from the first unfinished batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError

from trade_scout.data.backfill import (
    BackfillBatch,
    BackfillPlan,
    BackfillPlanError,
    BackfillRuntimeConflictError,
    BackfillRuntimeStore,
)
from trade_scout.data.provider import DailyBarRequest, ProviderAdapter, ProviderDailyBar


@dataclass(frozen=True, slots=True)
class BudgetedBackfillResult:
    """Progress from one bounded invocation of a larger durable backfill."""

    plan_id: str
    completed_batch_count: int
    pending_batch_count: int
    executed_batch_count: int
    record_count_this_run: int
    complete: bool
    rate_limited: bool
    rate_limited_batch_id: str | None = None


def execute_backfill_budget(
    adapter: ProviderAdapter,
    plan: BackfillPlan,
    store: BackfillRuntimeStore,
    *,
    max_batches_this_run: int,
) -> BudgetedBackfillResult:
    """Execute at most N pending batches and stop safely on provider throttling.

    Completed batches are persisted and checkpointed individually. If the provider
    returns HTTP 429, the current batch remains pending and the invocation exits with
    ``rate_limited=True`` rather than converting a quota event into a data gap.
    """

    if max_batches_this_run < 1:
        raise ValueError("max_batches_this_run must be positive")
    if adapter.provider_id != plan.provider_id:
        raise BackfillPlanError(
            f"adapter provider {adapter.provider_id} does not match plan provider "
            f"{plan.provider_id}"
        )

    checkpoint = store.checkpoint(plan)
    completed = set(checkpoint.completed_batch_ids)
    executed = 0
    records = 0
    rate_limited_batch_id: str | None = None

    for batch in plan.batches:
        if batch.batch_id in completed:
            continue
        if executed >= max_batches_this_run:
            break
        try:
            bars = tuple(adapter.get_daily_bars(_request(plan, batch)))
        except Exception as exc:
            if _is_http_429(exc):
                rate_limited_batch_id = batch.batch_id
                break
            raise

        _validate_response(adapter.provider_id, batch, bars)
        store.persist_batch(plan, batch, bars)
        store.mark_completed(plan, batch)
        completed.add(batch.batch_id)
        executed += 1
        records += len(bars)

    completed_count = len(completed)
    pending_count = len(plan.batches) - completed_count
    return BudgetedBackfillResult(
        plan_id=plan.plan_id,
        completed_batch_count=completed_count,
        pending_batch_count=pending_count,
        executed_batch_count=executed,
        record_count_this_run=records,
        complete=pending_count == 0,
        rate_limited=rate_limited_batch_id is not None,
        rate_limited_batch_id=rate_limited_batch_id,
    )


def _request(plan: BackfillPlan, batch: BackfillBatch) -> DailyBarRequest:
    return DailyBarRequest(
        start=batch.start,
        end=batch.end,
        provider_symbols=batch.provider_symbols,
        adjustment=plan.adjustment,
        run_id=f"backfill:{plan.plan_id}:{batch.batch_id}",
    )


def _is_http_429(exc: BaseException) -> bool:
    """Inspect an exception chain without depending on provider error message text."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, HTTPError) and current.code == 429:
            return True
        current = current.__cause__ or current.__context__
    return False


def _validate_response(
    provider_id: str,
    batch: BackfillBatch,
    bars: tuple[ProviderDailyBar, ...],
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
