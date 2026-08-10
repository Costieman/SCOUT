from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_scout.data.providers.tiingo_campaign_state import (
    RawStorageClass,
    TiingoCampaignStateError,
    advance_tiingo_safe_campaign_state,
    initial_tiingo_safe_campaign_state,
    load_tiingo_safe_campaign_state,
    persist_tiingo_safe_campaign_state,
)
from trade_scout.data.providers.tiingo_sp500_campaign import (
    TiingoSp500CampaignRun,
    TiingoSp500UniverseSnapshot,
)


def _snapshot() -> TiingoSp500UniverseSnapshot:
    return TiingoSp500UniverseSnapshot(
        snapshot_date=date(2026, 8, 10),
        symbols=("AAPL", "JPM", "MSFT"),
        sha256="abc123",
    )


def _run(
    *,
    executed: int = 1,
    rows: int = 100,
    rate_limited: bool = False,
    failed_symbol: str | None = None,
) -> TiingoSp500CampaignRun:
    return TiingoSp500CampaignRun(
        plan_version="plan-v1",
        universe_sha256="abc123",
        completed_symbol_count=executed,
        pending_symbol_count=3 - executed,
        executed_symbol_count=executed,
        acquired_row_count=rows,
        rate_limited=rate_limited,
        rate_limited_symbol="JPM" if rate_limited else None,
        failed_symbol=failed_symbol,
        failure_type="RuntimeError" if failed_symbol else None,
    )


def test_ephemeral_run_records_observation_but_not_durable_completion(tmp_path: Path) -> None:
    snapshot = _snapshot()
    initial = initial_tiingo_safe_campaign_state(
        campaign_id="tiingo-sp500",
        plan_version="plan-v1",
        snapshot=snapshot,
    )
    updated = advance_tiingo_safe_campaign_state(
        initial,
        run=_run(),
        snapshot=snapshot,
        storage_class=RawStorageClass.EPHEMERAL,
        completed_symbols_after_run=(),
        durable_row_count_this_run=0,
        observed_at=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )
    assert updated.run_count == 1
    assert updated.observed_row_count_total == 100
    assert updated.durable_completed_symbols == ()
    assert updated.durable_row_count_total == 0
    assert updated.last_status == "PROGRESSED"

    path = tmp_path / "state.json"
    persist_tiingo_safe_campaign_state(path, updated)
    assert load_tiingo_safe_campaign_state(path) == updated


def test_ephemeral_run_cannot_claim_durable_completion() -> None:
    snapshot = _snapshot()
    initial = initial_tiingo_safe_campaign_state(
        campaign_id="tiingo-sp500",
        plan_version="plan-v1",
        snapshot=snapshot,
    )
    with pytest.raises(TiingoCampaignStateError, match="ephemeral runs cannot advance"):
        advance_tiingo_safe_campaign_state(
            initial,
            run=_run(),
            snapshot=snapshot,
            storage_class=RawStorageClass.EPHEMERAL,
            completed_symbols_after_run=("AAPL",),
            durable_row_count_this_run=100,
            observed_at=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )


def test_durable_state_is_monotonic() -> None:
    snapshot = _snapshot()
    initial = initial_tiingo_safe_campaign_state(
        campaign_id="tiingo-sp500",
        plan_version="plan-v1",
        snapshot=snapshot,
    )
    first = advance_tiingo_safe_campaign_state(
        initial,
        run=_run(),
        snapshot=snapshot,
        storage_class=RawStorageClass.DURABLE,
        completed_symbols_after_run=("AAPL",),
        durable_row_count_this_run=100,
        observed_at=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )
    with pytest.raises(TiingoCampaignStateError, match="cannot move backwards"):
        advance_tiingo_safe_campaign_state(
            first,
            run=_run(executed=0, rows=0),
            snapshot=snapshot,
            storage_class=RawStorageClass.DURABLE,
            completed_symbols_after_run=(),
            durable_row_count_this_run=0,
            observed_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        )


def test_rate_limit_is_persisted_as_operational_state_not_missing_data() -> None:
    snapshot = _snapshot()
    initial = initial_tiingo_safe_campaign_state(
        campaign_id="tiingo-sp500",
        plan_version="plan-v1",
        snapshot=snapshot,
    )
    updated = advance_tiingo_safe_campaign_state(
        initial,
        run=_run(executed=0, rows=0, rate_limited=True),
        snapshot=snapshot,
        storage_class=RawStorageClass.EPHEMERAL,
        completed_symbols_after_run=(),
        durable_row_count_this_run=0,
        observed_at=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )
    assert updated.last_status == "PAUSED_RATE_LIMITED"
    assert updated.quota_pause_count == 1
    assert updated.last_rate_limited_symbol == "JPM"
    assert updated.durable_completed_symbols == ()
