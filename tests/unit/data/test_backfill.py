from datetime import date

import pytest

from trade_scout.data.backfill import (
    BackfillExecutionError,
    BackfillPlanError,
    BackfillRuntimeConflictError,
    BackfillRuntimeStore,
    execute_daily_bar_backfill,
    plan_daily_bar_backfill,
)
from trade_scout.data.provider import DailyBarRequest, ProviderDailyBar


class FakeBackfillAdapter:
    provider_id = "fake"

    def __init__(self, *, fail_once_on: date | None = None, wrong_symbol: bool = False) -> None:
        self.fail_once_on = fail_once_on
        self.wrong_symbol = wrong_symbol
        self.failed = False
        self.calls: list[DailyBarRequest] = []

    def get_daily_bars(self, request: DailyBarRequest) -> tuple[ProviderDailyBar, ...]:
        self.calls.append(request)
        if self.fail_once_on == request.start and not self.failed:
            self.failed = True
            raise RuntimeError("simulated provider interruption")
        symbol = "WRONG" if self.wrong_symbol else request.provider_symbols[0]
        return (
            ProviderDailyBar(
                provider_id=self.provider_id,
                provider_instrument_id=f"id-{symbol}",
                symbol=symbol,
                trade_date=request.start,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1_000_000.25,
                split_factor=1.0,
                dividend_cash=0.0,
            ),
        )


def test_plan_is_deterministic_and_bounded() -> None:
    kwargs = {
        "provider_id": "fake",
        "provider_symbols": ("CCC", "AAA", "BBB"),
        "start": date(2026, 1, 1),
        "end": date(2026, 1, 5),
        "max_calendar_days_per_batch": 2,
        "max_symbols_per_batch": 2,
    }

    first = plan_daily_bar_backfill(**kwargs)
    second = plan_daily_bar_backfill(**kwargs)

    assert first == second
    assert first.provider_symbols == ("AAA", "BBB", "CCC")
    assert len(first.batches) == 6
    assert [(batch.start, batch.end) for batch in first.batches] == [
        (date(2026, 1, 1), date(2026, 1, 2)),
        (date(2026, 1, 1), date(2026, 1, 2)),
        (date(2026, 1, 3), date(2026, 1, 4)),
        (date(2026, 1, 3), date(2026, 1, 4)),
        (date(2026, 1, 5), date(2026, 1, 5)),
        (date(2026, 1, 5), date(2026, 1, 5)),
    ]
    assert [batch.provider_symbols for batch in first.batches] == [
        ("AAA", "BBB"),
        ("CCC",),
        ("AAA", "BBB"),
        ("CCC",),
        ("AAA", "BBB"),
        ("CCC",),
    ]


def test_plan_rejects_duplicate_symbols() -> None:
    with pytest.raises(BackfillPlanError, match="duplicates"):
        plan_daily_bar_backfill(
            provider_id="fake",
            provider_symbols=("AAA", "AAA"),
            start=date(2026, 1, 1),
            end=date(2026, 1, 2),
            max_calendar_days_per_batch=1,
            max_symbols_per_batch=1,
        )


def test_execution_resumes_after_completed_staged_batch(tmp_path) -> None:
    plan = plan_daily_bar_backfill(
        provider_id="fake",
        provider_symbols=("AAA",),
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
        max_calendar_days_per_batch=1,
        max_symbols_per_batch=1,
    )
    store = BackfillRuntimeStore(tmp_path)
    adapter = FakeBackfillAdapter(fail_once_on=date(2026, 1, 2))

    with pytest.raises(BackfillExecutionError) as error:
        execute_daily_bar_backfill(adapter, plan, store)

    assert error.value.batch_id == plan.batches[1].batch_id
    assert store.checkpoint(plan).completed_batch_ids == (plan.batches[0].batch_id,)

    result = execute_daily_bar_backfill(adapter, plan, store)

    assert result.batch_count == 2
    assert result.record_count == 2
    assert [bar.trade_date for bar in result.bars] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert result.bars[0].volume == 1_000_000.25
    assert [request.start for request in adapter.calls] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 2),
    ]


def test_staged_batch_is_immutable(tmp_path) -> None:
    plan = plan_daily_bar_backfill(
        provider_id="fake",
        provider_symbols=("AAA",),
        start=date(2026, 1, 1),
        end=date(2026, 1, 1),
        max_calendar_days_per_batch=1,
        max_symbols_per_batch=1,
    )
    store = BackfillRuntimeStore(tmp_path)
    batch = plan.batches[0]
    first = FakeBackfillAdapter().get_daily_bars(
        DailyBarRequest(start=batch.start, end=batch.end, provider_symbols=("AAA",))
    )
    changed = (
        ProviderDailyBar(
            provider_id="fake",
            provider_instrument_id="id-AAA",
            symbol="AAA",
            trade_date=date(2026, 1, 1),
            open=100.0,
            high=101.0,
            low=99.0,
            close=99.0,
            volume=1_000_000.25,
            split_factor=1.0,
            dividend_cash=0.0,
        ),
    )

    store.persist_batch(plan, batch, first)
    store.persist_batch(plan, batch, first)

    with pytest.raises(BackfillRuntimeConflictError, match="different content"):
        store.persist_batch(plan, batch, changed)


def test_execution_rejects_out_of_scope_provider_response(tmp_path) -> None:
    plan = plan_daily_bar_backfill(
        provider_id="fake",
        provider_symbols=("AAA",),
        start=date(2026, 1, 1),
        end=date(2026, 1, 1),
        max_calendar_days_per_batch=1,
        max_symbols_per_batch=1,
    )

    with pytest.raises(BackfillRuntimeConflictError, match="unexpected symbol"):
        execute_daily_bar_backfill(
            FakeBackfillAdapter(wrong_symbol=True),
            plan,
            BackfillRuntimeStore(tmp_path),
        )


def test_execution_rejects_provider_mismatch(tmp_path) -> None:
    plan = plan_daily_bar_backfill(
        provider_id="other",
        provider_symbols=("AAA",),
        start=date(2026, 1, 1),
        end=date(2026, 1, 1),
        max_calendar_days_per_batch=1,
        max_symbols_per_batch=1,
    )

    with pytest.raises(BackfillPlanError, match="does not match"):
        execute_daily_bar_backfill(
            FakeBackfillAdapter(),
            plan,
            BackfillRuntimeStore(tmp_path),
        )
