from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import pytest

from trade_scout.data.providers.tiingo_sp500_campaign import (
    TiingoSp500CampaignError,
    TiingoSp500CampaignPlan,
    parse_tiingo_sp500_universe,
    run_tiingo_sp500_campaign,
)


class FakeClient:
    def __init__(self, *, rate_limit_symbol: str | None = None) -> None:
        self.rate_limit_symbol = rate_limit_symbol
        self.calls: list[str] = []

    def get_json(self, endpoint: str, parameters=None):
        del parameters
        symbol = endpoint.split("/")[3]
        self.calls.append(symbol)
        if symbol == self.rate_limit_symbol:
            error = HTTPError(endpoint, 429, "Too Many Requests", hdrs=None, fp=None)
            try:
                raise error
            except HTTPError as exc:
                raise RuntimeError("provider throttle") from exc
        return [
            {
                "date": "2026-08-07T00:00:00.000Z",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 100.0,
                "divCash": 0.0,
                "splitFactor": 1.0,
            }
        ]


def _plan() -> TiingoSp500CampaignPlan:
    return TiingoSp500CampaignPlan(
        plan_version="test-v0.1",
        universe_source_url="https://example.invalid/sp500.csv",
        expected_snapshot_date=date(2026, 8, 10),
        expected_constituent_count=3,
        history_start=date(1996, 1, 2),
        history_end=date(2026, 8, 7),
        max_symbols_per_run=2,
    )


def _csv(snapshot_date: str = "2026-08-10") -> bytes:
    return (
        "symbol,date,gics sector,cik\n"
        f"MSFT,{snapshot_date},Information Technology,789019\n"
        f"AAPL,{snapshot_date},Information Technology,320193\n"
        f"JPM,{snapshot_date},Financials,19617\n"
    ).encode()


def _share_class_csv() -> bytes:
    return (
        b"symbol,date,gics sector,cik\n"
        b"BRK.B,2026-08-10,Financials,1067983\n"
        b"AAPL,2026-08-10,Information Technology,320193\n"
        b"JPM,2026-08-10,Financials,19617\n"
    )


def test_universe_snapshot_is_sorted_and_hashed() -> None:
    snapshot = parse_tiingo_sp500_universe(_csv(), _plan())
    assert snapshot.symbols == ("AAPL", "JPM", "MSFT")
    assert len(snapshot.sha256) == 64


def test_stale_universe_snapshot_fails_closed() -> None:
    with pytest.raises(TiingoSp500CampaignError, match="snapshot date"):
        parse_tiingo_sp500_universe(_csv("2026-08-09"), _plan())


def test_campaign_budgets_and_resumes_from_checkpoint(tmp_path: Path) -> None:
    plan = _plan()
    snapshot = parse_tiingo_sp500_universe(_csv(), plan)
    state = tmp_path / "checkpoint.json"

    first_client = FakeClient()
    first = run_tiingo_sp500_campaign(first_client, plan, snapshot, state)
    assert first.executed_symbol_count == 2
    assert first.completed_symbol_count == 2
    assert first.pending_symbol_count == 1
    assert first_client.calls == ["AAPL", "JPM"]

    second_client = FakeClient()
    second = run_tiingo_sp500_campaign(second_client, plan, snapshot, state)
    assert second.executed_symbol_count == 1
    assert second.completed_symbol_count == 3
    assert second.pending_symbol_count == 0
    assert second_client.calls == ["MSFT"]


def test_campaign_queries_provider_symbol_but_tracks_source_symbol(tmp_path: Path) -> None:
    plan = _plan()
    snapshot = parse_tiingo_sp500_universe(_share_class_csv(), plan)
    state = tmp_path / "checkpoint.json"

    first_client = FakeClient()
    first = run_tiingo_sp500_campaign(
        first_client,
        plan,
        snapshot,
        state,
        max_symbols_this_run=2,
    )
    assert first_client.calls == ["AAPL", "BRK-B"]
    assert first.completed_symbol_count == 2

    second_client = FakeClient()
    second = run_tiingo_sp500_campaign(
        second_client,
        plan,
        snapshot,
        state,
        max_symbols_this_run=2,
    )
    assert second_client.calls == ["JPM"]
    assert second.completed_symbol_count == 3


def test_rate_limit_leaves_current_symbol_pending(tmp_path: Path) -> None:
    plan = _plan()
    snapshot = parse_tiingo_sp500_universe(_csv(), plan)
    result = run_tiingo_sp500_campaign(
        FakeClient(rate_limit_symbol="JPM"),
        plan,
        snapshot,
        tmp_path / "checkpoint.json",
        max_symbols_this_run=3,
    )
    assert result.rate_limited
    assert result.rate_limited_symbol == "JPM"
    assert result.completed_symbol_count == 1
    assert result.pending_symbol_count == 2
    assert result.failed_symbol is None
