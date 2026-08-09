from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest, DataFamily, ProviderHealthStatus
from trade_scout.data.providers.stooq import (
    StooqAdapter,
    StooqApiError,
    StooqIdentityError,
    StooqInstrumentLink,
    StooqResponseError,
    StooqUnsupportedError,
)


class FixtureStooqClient:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, date, date]] = []

    def get_csv(self, *, symbol: str, start: date, end: date) -> bytes:
        self.calls.append((symbol, start, end))
        try:
            return self.responses[symbol]
        except KeyError as exc:
            raise StooqApiError(f"no fixture for {symbol}") from exc


def _adapter(client: FixtureStooqClient) -> StooqAdapter:
    return StooqAdapter(
        client,
        instrument_links=(
            StooqInstrumentLink(
                query_symbol="AAPL.US",
                provider_instrument_id="reviewed:stooq:aapl-us",
            ),
        ),
    )


def test_stooq_maps_bounded_csv_without_inventing_adjustments() -> None:
    client = FixtureStooqClient(
        {
            "AAPL.US": (
                b"Date,Open,High,Low,Close,Volume\n"
                b"2026-08-06,210.0,214.0,209.5,213.2,54321000\n"
                b"2026-08-07,213.5,216.0,212.0,215.7,49876543\n"
            )
        }
    )
    adapter = _adapter(client)

    bars = adapter.get_daily_bars(
        DailyBarRequest(
            start=date(2026, 8, 6),
            end=date(2026, 8, 7),
            provider_symbols=("aapl.us",),
        )
    )

    assert len(bars) == 2
    assert bars[0].provider_id == "stooq"
    assert bars[0].provider_instrument_id == "reviewed:stooq:aapl-us"
    assert bars[0].symbol == "AAPL.US"
    assert bars[0].trade_date == date(2026, 8, 6)
    assert bars[0].open == 210.0
    assert bars[0].high == 214.0
    assert bars[0].low == 209.5
    assert bars[0].close == 213.2
    assert bars[0].volume == 54321000.0
    assert bars[0].split_factor is None
    assert bars[0].dividend_cash is None
    assert bars[0].adjusted_close is None
    assert client.calls == [("AAPL.US", date(2026, 8, 6), date(2026, 8, 7))]


def test_stooq_capabilities_are_deliberately_narrow() -> None:
    adapter = _adapter(FixtureStooqClient({"AAPL.US": b"No data"}))

    capabilities = adapter.describe_capabilities()

    assert capabilities.data_families == frozenset({DataFamily.DAILY_BARS})
    assert capabilities.adjustment_modes == frozenset({PriceRepresentation.RAW})
    assert capabilities.supports_delisted is False
    assert capabilities.supports_symbol_history is False
    assert any("adjustment semantics" in item for item in capabilities.known_limitations)
    assert any("licensing" in item for item in capabilities.known_limitations)


def test_stooq_requires_explicit_identity_link() -> None:
    adapter = _adapter(FixtureStooqClient({"MSFT.US": b"No data"}))

    with pytest.raises(StooqIdentityError, match="no explicit provider identity link"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 8, 6),
                end=date(2026, 8, 7),
                provider_symbols=("MSFT.US",),
            )
        )


def test_stooq_rejects_unaccepted_adjusted_request() -> None:
    adapter = _adapter(FixtureStooqClient({"AAPL.US": b"No data"}))

    with pytest.raises(StooqUnsupportedError, match="adjustment semantics"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 8, 6),
                end=date(2026, 8, 7),
                provider_symbols=("AAPL.US",),
                adjustment=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )


def test_stooq_rejects_malformed_csv() -> None:
    adapter = _adapter(
        FixtureStooqClient(
            {"AAPL.US": b"Date,Open,High,Low,Close\n2026-08-07,1,2,1,2\n"}
        )
    )

    with pytest.raises(StooqResponseError, match="missing required"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 8, 7),
                end=date(2026, 8, 7),
                provider_symbols=("AAPL.US",),
            )
        )


def test_stooq_rejects_out_of_scope_dates() -> None:
    adapter = _adapter(
        FixtureStooqClient(
            {
                "AAPL.US": (
                    b"Date,Open,High,Low,Close,Volume\n"
                    b"2026-08-05,1,2,1,2,100\n"
                )
            }
        )
    )

    with pytest.raises(StooqResponseError, match="outside requested range"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 8, 6),
                end=date(2026, 8, 7),
                provider_symbols=("AAPL.US",),
            )
        )


def test_stooq_explicitly_refuses_unclaimed_reference_capabilities() -> None:
    adapter = _adapter(FixtureStooqClient({"AAPL.US": b"No data"}))

    with pytest.raises(StooqUnsupportedError, match="instrument master"):
        adapter.get_instruments()
    with pytest.raises(StooqUnsupportedError, match="symbol history"):
        adapter.get_symbol_history()


def test_stooq_health_probe_reports_http_success_as_connectivity_health() -> None:
    adapter = _adapter(FixtureStooqClient({"AAPL.US": b"No data"}))

    health = adapter.health_check()

    assert health.status is ProviderHealthStatus.HEALTHY
