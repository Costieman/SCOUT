from datetime import date
from pathlib import Path
from urllib.error import HTTPError

from trade_scout.data.backfill import BackfillRuntimeStore, plan_daily_bar_backfill
from trade_scout.data.budgeted_backfill import execute_backfill_budget
from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest, ProviderDailyBar


class FakeAdapter:
    provider_id = "tiingo"

    def __init__(self, *, rate_limit_on_call: int | None = None) -> None:
        self.calls = 0
        self.rate_limit_on_call = rate_limit_on_call

    def get_daily_bars(self, request: DailyBarRequest) -> tuple[ProviderDailyBar, ...]:
        self.calls += 1
        if self.rate_limit_on_call == self.calls:
            http_error = HTTPError(
                "https://api.tiingo.com/test",
                429,
                "Too Many Requests",
                hdrs=None,
                fp=None,
            )
            try:
                raise http_error
            except HTTPError as exc:
                raise RuntimeError("provider throttle") from exc
        symbol = request.provider_symbols[0]
        return (
            ProviderDailyBar(
                provider_id=self.provider_id,
                provider_instrument_id=f"tiingo:{symbol}",
                symbol=symbol,
                trade_date=request.start,
                open=10.0,
                high=11.0,
                low=9.0,
                close=10.5,
                volume=100.0,
                split_factor=None,
                dividend_cash=None,
            ),
        )


def _plan():
    return plan_daily_bar_backfill(
        provider_id="tiingo",
        provider_symbols=("AAPL", "JPM", "MSFT"),
        start=date(2026, 8, 7),
        end=date(2026, 8, 7),
        max_calendar_days_per_batch=365,
        max_symbols_per_batch=1,
        adjustment=PriceRepresentation.RAW,
    )


def test_budget_stops_after_requested_number_and_resumes(tmp_path: Path) -> None:
    plan = _plan()
    store = BackfillRuntimeStore(tmp_path)
    first_adapter = FakeAdapter()

    first = execute_backfill_budget(
        first_adapter,
        plan,
        store,
        max_batches_this_run=2,
    )
    assert first.executed_batch_count == 2
    assert first.completed_batch_count == 2
    assert first.pending_batch_count == 1
    assert not first.complete
    assert not first.rate_limited

    second_adapter = FakeAdapter()
    second = execute_backfill_budget(
        second_adapter,
        plan,
        store,
        max_batches_this_run=2,
    )
    assert second.executed_batch_count == 1
    assert second.completed_batch_count == 3
    assert second.pending_batch_count == 0
    assert second.complete
    assert second_adapter.calls == 1


def test_http_429_preserves_completed_batches_and_current_batch_pending(tmp_path: Path) -> None:
    plan = _plan()
    store = BackfillRuntimeStore(tmp_path)
    adapter = FakeAdapter(rate_limit_on_call=2)

    result = execute_backfill_budget(
        adapter,
        plan,
        store,
        max_batches_this_run=3,
    )
    assert result.executed_batch_count == 1
    assert result.completed_batch_count == 1
    assert result.pending_batch_count == 2
    assert result.rate_limited
    assert result.rate_limited_batch_id == plan.batches[1].batch_id

    checkpoint = store.checkpoint(plan)
    assert checkpoint.completed_batch_ids == (plan.batches[0].batch_id,)


def test_rate_limit_is_not_misclassified_as_complete(tmp_path: Path) -> None:
    plan = _plan()
    store = BackfillRuntimeStore(tmp_path)
    result = execute_backfill_budget(
        FakeAdapter(rate_limit_on_call=1),
        plan,
        store,
        max_batches_this_run=1,
    )
    assert result.rate_limited
    assert not result.complete
    assert result.record_count_this_run == 0
