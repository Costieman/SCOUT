from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pytest

from trade_scout.data.contracts import PriceRepresentation, SecurityType
from trade_scout.data.provider import DailyBarRequest, DataFamily
from trade_scout.data.providers.alpha_vantage import (
    AlphaVantageAdapter,
    AlphaVantageApiError,
    AlphaVantageCapabilityError,
    AlphaVantageHttpClient,
    AlphaVantageResponseError,
)
from trade_scout.data.raw_store import Primitive


class FakeCsvClient:
    def __init__(self, responses: Mapping[tuple[tuple[str, Primitive], ...], bytes]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Primitive]] = []

    def get_csv(self, parameters: Mapping[str, Primitive]) -> bytes:
        materialized = dict(parameters)
        self.calls.append(materialized)
        key = tuple(sorted(materialized.items()))
        return self._responses[key]


def _key(**parameters: Primitive) -> tuple[tuple[str, Primitive], ...]:
    return tuple(sorted(parameters.items()))


def test_listing_status_maps_active_and_delisted_point_in_time_records() -> None:
    active = (
        b"symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
        b"IBM,International Business Machines,NYSE,Stock,1915-11-11,null,Active\n"
        b"SPY,SPDR S&P 500 ETF Trust,NYSE Arca,ETF,1993-01-29,null,Active\n"
    )
    delisted = (
        b"symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
        b"OLD,Old Example Corp,NASDAQ,Stock,2001-05-01,2014-03-14,Delisted\n"
    )
    as_of = date(2014, 7, 10)
    client = FakeCsvClient(
        {
            _key(function="LISTING_STATUS", state="active", date=as_of.isoformat()): active,
            _key(function="LISTING_STATUS", state="delisted", date=as_of.isoformat()): delisted,
        }
    )
    adapter = AlphaVantageAdapter(client)

    instruments = adapter.get_instruments(as_of=as_of)

    assert [instrument.symbol for instrument in instruments] == ["IBM", "SPY", "OLD"]
    ibm = instruments[0]
    assert ibm.provider_id == "alpha_vantage"
    assert ibm.provider_instrument_id == "alpha_vantage:symbol:IBM"
    assert ibm.security_type is SecurityType.COMMON_STOCK
    assert ibm.first_trade_date == date(1915, 11, 11)
    assert ibm.end_date is None
    assert ibm.active is True
    assert ibm.source_fields["metadata_quality"] == "PASS"
    old = instruments[2]
    assert old.active is False
    assert old.end_date == date(2014, 3, 14)
    assert "not permanent canonical identity" in str(old.source_fields["identity_warning"])
    assert client.calls == [
        {"function": "LISTING_STATUS", "state": "active", "date": "2014-07-10"},
        {"function": "LISTING_STATUS", "state": "delisted", "date": "2014-07-10"},
    ]


def test_blank_listing_name_is_retained_as_warn_metadata_not_rejected() -> None:
    active = (
        b"symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
        b"ARGD,,NYSE,Stock,2002-12-10,null,Active\n"
    )
    delisted = b"symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
    as_of = date(2014, 7, 10)
    client = FakeCsvClient(
        {
            _key(function="LISTING_STATUS", state="active", date=as_of.isoformat()): active,
            _key(function="LISTING_STATUS", state="delisted", date=as_of.isoformat()): delisted,
        }
    )

    instrument = AlphaVantageAdapter(client).get_instruments(as_of=as_of)[0]

    assert instrument.symbol == "ARGD"
    assert instrument.name == ""
    assert instrument.source_fields["name_missing"] is True
    assert instrument.source_fields["metadata_quality"] == "WARN"


def test_capability_declaration_is_conservative() -> None:
    adapter = AlphaVantageAdapter(FakeCsvClient({}))

    capabilities = adapter.describe_capabilities()

    assert capabilities.provider_id == "alpha_vantage"
    assert capabilities.data_families == frozenset(
        {DataFamily.INSTRUMENTS, DataFamily.STATUS_DELISTINGS, DataFamily.DAILY_BARS}
    )
    assert capabilities.adjustment_modes == frozenset({PriceRepresentation.RAW})
    assert capabilities.supports_delisted is True
    assert capabilities.supports_symbol_history is False
    assert capabilities.earliest_daily_bar_date is None
    assert any("blank company names" in item for item in capabilities.known_limitations)
    assert any("full output is plan-dependent" in item for item in capabilities.known_limitations)


def test_compact_daily_bars_are_filtered_to_requested_dates() -> None:
    payload = (
        b"timestamp,open,high,low,close,volume\n"
        b"2026-08-07,101.0,103.0,100.0,102.5,2000000\n"
        b"2026-08-06,99.0,102.0,98.0,101.0,1800000\n"
        b"2026-08-05,97.0,100.0,96.0,99.0,1700000\n"
    )
    client = FakeCsvClient(
        {
            _key(
                function="TIME_SERIES_DAILY",
                symbol="IBM",
                outputsize="compact",
                datatype="csv",
            ): payload
        }
    )
    adapter = AlphaVantageAdapter(client)

    bars = adapter.get_daily_bars(
        DailyBarRequest(
            start=date(2026, 8, 6),
            end=date(2026, 8, 7),
            provider_symbols=("IBM",),
        )
    )

    assert [bar.trade_date for bar in bars] == [date(2026, 8, 6), date(2026, 8, 7)]
    assert bars[0].provider_instrument_id == "alpha_vantage:symbol:IBM"
    assert bars[0].open == 99.0
    assert bars[1].close == 102.5
    assert bars[1].volume == 2_000_000.0


def test_long_history_is_not_silently_requested_with_unverified_free_entitlement() -> None:
    adapter = AlphaVantageAdapter(FakeCsvClient({}))

    with pytest.raises(AlphaVantageCapabilityError, match="full-output entitlement"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2010, 1, 4),
                end=date(2026, 8, 7),
                provider_symbols=("IBM",),
            )
        )


def test_full_history_can_be_explicitly_enabled_after_entitlement_verification() -> None:
    payload = b"timestamp,open,high,low,close,volume\n2010-01-04,10.0,11.0,9.5,10.5,1000\n"
    client = FakeCsvClient(
        {
            _key(
                function="TIME_SERIES_DAILY",
                symbol="IBM",
                outputsize="full",
                datatype="csv",
            ): payload
        }
    )
    adapter = AlphaVantageAdapter(client, allow_full_history=True)

    bars = adapter.get_daily_bars(
        DailyBarRequest(
            start=date(2010, 1, 4),
            end=date(2010, 1, 4),
            provider_symbols=("IBM",),
        )
    )

    assert len(bars) == 1
    assert client.calls[0]["outputsize"] == "full"


def test_symbol_history_and_corporate_actions_fail_explicitly() -> None:
    adapter = AlphaVantageAdapter(FakeCsvClient({}))

    with pytest.raises(AlphaVantageCapabilityError, match="permanent symbol history"):
        adapter.get_symbol_history()


def test_historical_listing_status_before_supported_boundary_fails() -> None:
    adapter = AlphaVantageAdapter(FakeCsvClient({}))

    with pytest.raises(AlphaVantageCapabilityError, match="later than 2010-01-01"):
        adapter.get_instruments(as_of=date(2010, 1, 1))


def test_http_client_surfaces_rate_limit_json_instead_of_parsing_it_as_csv() -> None:
    class FakeTransport:
        def get(self, url: str, *, timeout: float) -> bytes:
            del url, timeout
            return b'{"Information":"API rate limit reached"}'

    client = AlphaVantageHttpClient("secret", transport=FakeTransport())

    with pytest.raises(AlphaVantageApiError, match="rate limit reached"):
        client.get_csv({"function": "LISTING_STATUS", "state": "active"})


def test_malformed_daily_csv_fails_visibly() -> None:
    payload = b"date,open,high,low,close,volume\n2026-08-07,1,2,1,2,10\n"
    client = FakeCsvClient(
        {
            _key(
                function="TIME_SERIES_DAILY",
                symbol="IBM",
                outputsize="compact",
                datatype="csv",
            ): payload
        }
    )
    adapter = AlphaVantageAdapter(client)

    with pytest.raises(AlphaVantageResponseError, match="missing timestamp"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 8, 7),
                end=date(2026, 8, 7),
                provider_symbols=("IBM",),
            )
        )
