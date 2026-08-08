import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation
from trade_scout.data.provider import CorporateActionRequest, DailyBarRequest, ProviderAdapter
from trade_scout.data.providers.massive import (
    MassiveAdapter,
    MassiveApiError,
    MassiveHttpClient,
    MassiveIdentityError,
    RawStoreCapture,
)
from trade_scout.data.raw_store import Primitive, RawBatchStore


class FakeMassiveClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Primitive]]] = []

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> Mapping[str, object]:
        params = dict(parameters or {})
        self.calls.append((endpoint, params))

        if endpoint == "/v3/reference/tickers":
            ticker = params.get("ticker")
            active = params.get("active")
            if ticker == "AAA":
                if active is True:
                    return {"results": [_ticker_record(active=True)]}
                return {"results": []}
            if ticker == "OLD":
                if active is False:
                    return {"results": [_ticker_record(ticker="OLD", active=False)]}
                return {"results": []}
            if ticker == "NEW":
                if active is True:
                    return {"results": [_ticker_record(ticker="NEW", active=True)]}
                return {"results": []}
            if params.get("limit") == 1:
                return {"results": [_ticker_record(active=True)]}
            if active is True:
                return {"results": [_ticker_record(active=True)]}
            return {
                "results": [
                    _ticker_record(
                        ticker="DEL",
                        active=False,
                        figi="BBG000DELST1",
                        delisted="2020-06-30T00:00:00Z",
                    )
                ]
            }

        if endpoint.endswith("/events"):
            return {
                "results": {
                    "events": [
                        {
                            "date": "2010-01-04",
                            "type": "ticker_change",
                            "ticker_change": {"ticker": "OLD"},
                        },
                        {
                            "date": "2020-07-01",
                            "type": "ticker_change",
                            "ticker_change": {"ticker": "NEW"},
                        },
                    ],
                    "name": "Example Corp",
                }
            }

        if endpoint.startswith("/v2/aggs/ticker/AAA/"):
            adjusted = params.get("adjusted")
            if adjusted is False:
                return {
                    "results": [
                        {
                            "t": 1786075200000,
                            "o": 100,
                            "h": 105,
                            "l": 99,
                            "c": 103,
                            "v": 1_000_000.375,
                        }
                    ]
                }
            return {
                "results": [
                    {
                        "t": 1786075200000,
                        "o": 50,
                        "h": 52.5,
                        "l": 49.5,
                        "c": 51.5,
                        "v": 2_000_000.75,
                    }
                ]
            }

        if endpoint == "/stocks/v1/dividends":
            return {
                "results": [
                    {
                        "id": "div-1",
                        "ticker": "AAA",
                        "ex_dividend_date": "2026-08-07",
                        "cash_amount": 0.25,
                    }
                ]
            }

        if endpoint == "/stocks/v1/splits":
            return {
                "results": [
                    {
                        "id": "split-1",
                        "ticker": "AAA",
                        "execution_date": "2026-08-07",
                        "adjustment_type": "forward_split",
                        "split_from": 1,
                        "split_to": 2,
                    }
                ]
            }

        raise AssertionError(f"unexpected Massive request: {endpoint} {params}")


def _ticker_record(
    *,
    ticker: str = "AAA",
    active: bool,
    figi: str = "BBG000EXAMPL",
    delisted: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "ticker": ticker,
        "name": "Example Corp",
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNYS",
        "type": "CS",
        "currency_name": "usd",
        "active": active,
        "composite_figi": figi,
        "share_class_figi": figi + "S",
        "cik": "0000000001",
    }
    if delisted is not None:
        result["delisted_utc"] = delisted
    return result


def test_massive_adapter_satisfies_provider_protocol_and_declares_limitations() -> None:
    adapter = MassiveAdapter(FakeMassiveClient())

    assert isinstance(adapter, ProviderAdapter)
    capabilities = adapter.describe_capabilities()
    assert capabilities.supports_delisted is True
    assert capabilities.supports_symbol_history is True
    assert capabilities.earliest_daily_bar_date == date(2003, 9, 10)
    assert PriceRepresentation.RAW in capabilities.adjustment_modes
    assert PriceRepresentation.SPLIT_ADJUSTED in capabilities.adjustment_modes
    assert any("experimental" in item for item in capabilities.known_limitations)


def test_reference_mapping_uses_figi_identity_and_retains_delisted_records() -> None:
    adapter = MassiveAdapter(FakeMassiveClient())

    instruments = adapter.get_instruments(as_of=date(2020, 6, 30))

    by_symbol = {instrument.symbol: instrument for instrument in instruments}
    assert by_symbol["AAA"].provider_instrument_id == "BBG000EXAMPL"
    assert by_symbol["AAA"].security_type.value == "common_stock"
    assert by_symbol["DEL"].active is False
    assert by_symbol["DEL"].end_date == date(2020, 6, 30)
    assert by_symbol["AAA"].first_trade_date is None


def test_daily_bars_pair_raw_and_split_adjusted_responses_and_attach_dividend() -> None:
    adapter = MassiveAdapter(FakeMassiveClient())

    bars = adapter.get_daily_bars(
        DailyBarRequest(
            start=date(2026, 8, 7),
            end=date(2026, 8, 7),
            provider_symbols=("AAA",),
        )
    )

    assert len(bars) == 1
    bar = bars[0]
    assert bar.provider_instrument_id == "BBG000EXAMPL"
    assert bar.trade_date == date(2026, 8, 7)
    assert bar.close == 103.0
    assert bar.adjusted_close == 51.5
    assert bar.split_factor == 0.5
    assert bar.dividend_cash == 0.25
    assert bar.volume == 1_000_000.375


def test_corporate_actions_map_split_and_cash_dividend_without_blending() -> None:
    adapter = MassiveAdapter(FakeMassiveClient())

    actions = adapter.get_corporate_actions(
        CorporateActionRequest(
            start=date(2026, 8, 1),
            end=date(2026, 8, 31),
            provider_symbols=("AAA",),
        )
    )

    assert {action.action_type for action in actions} == {
        CorporateActionType.SPLIT,
        CorporateActionType.CASH_DIVIDEND,
    }
    assert all(action.provider_instrument_id == "BBG000EXAMPL" for action in actions)
    assert {action.source_event_id for action in actions} == {"split-1", "div-1"}


def test_symbol_history_queries_by_stable_identifier_and_builds_dated_intervals() -> None:
    client = FakeMassiveClient()
    adapter = MassiveAdapter(client)

    history = adapter.get_symbol_history(provider_instrument_ids=("BBG000EXAMPL",))

    assert [(record.symbol, record.effective_from, record.effective_to) for record in history] == [
        ("OLD", date(2010, 1, 4), date(2020, 6, 30)),
        ("NEW", date(2020, 7, 1), None),
    ]
    assert client.calls[0][0] == "/vX/reference/tickers/BBG000EXAMPL/events"


def test_symbol_history_allows_bounded_reference_lag_without_changing_identity() -> None:
    class DelayedReferenceClient(FakeMassiveClient):
        def get_json(
            self,
            endpoint: str,
            parameters: Mapping[str, Primitive] | None = None,
        ) -> Mapping[str, object]:
            params = dict(parameters or {})
            if (
                endpoint == "/v3/reference/tickers"
                and params.get("ticker") == "OLD"
                and params.get("date") in {"2010-01-04", "2010-01-05"}
            ):
                self.calls.append((endpoint, params))
                return {"results": []}
            return super().get_json(endpoint, parameters)

    client = DelayedReferenceClient()
    adapter = MassiveAdapter(client)

    history = adapter.get_symbol_history(provider_instrument_ids=("BBG000EXAMPL",))

    assert history[0].symbol == "OLD"
    assert history[0].effective_from == date(2010, 1, 4)
    assert any(
        endpoint == "/v3/reference/tickers"
        and params.get("ticker") == "OLD"
        and params.get("date") == "2010-01-06"
        for endpoint, params in client.calls
    )


def test_symbol_identity_ambiguity_fails_instead_of_using_ticker_as_identity() -> None:
    class AmbiguousClient(FakeMassiveClient):
        def get_json(
            self,
            endpoint: str,
            parameters: Mapping[str, Primitive] | None = None,
        ) -> Mapping[str, object]:
            params = dict(parameters or {})
            if endpoint == "/v3/reference/tickers" and params.get("ticker") == "AAA":
                if params.get("active") is True:
                    return {"results": [_ticker_record(active=True, figi="FIGI-1")]}
                return {"results": [_ticker_record(active=False, figi="FIGI-2")]}
            return super().get_json(endpoint, parameters)

    adapter = MassiveAdapter(AmbiguousClient())

    with pytest.raises(MassiveIdentityError):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 8, 7),
                end=date(2026, 8, 7),
                provider_symbols=("AAA",),
            )
        )


class FakeBytesTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, *, timeout: float) -> bytes:
        assert timeout > 0
        self.urls.append(url)
        return self.payload


def test_http_client_keeps_api_key_out_of_raw_manifest(tmp_path) -> None:
    transport = FakeBytesTransport(json.dumps({"results": []}).encode())
    store = RawBatchStore(tmp_path)
    capture = RawStoreCapture(
        store,
        clock=lambda: datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        id_factory=lambda: "batch-1",
    )
    client = MassiveHttpClient("secret-key", transport=transport, raw_capture=capture)

    client.get_json("/v3/reference/tickers", {"market": "stocks", "limit": 1})

    parsed_url = urlsplit(transport.urls[0])
    assert parse_qs(parsed_url.query)["apiKey"] == ["secret-key"]
    manifest, payload = store.read(tmp_path / "massive" / "2026-08-08" / "massive-batch-1")
    assert payload == json.dumps({"results": []}).encode()
    assert "apiKey" not in manifest.request_parameters
    assert "secret-key" not in json.dumps(dict(manifest.request_parameters))
    assert manifest.endpoint == "/v3/reference/tickers"


def test_http_client_refuses_pagination_url_on_another_host() -> None:
    client = MassiveHttpClient(
        "secret-key",
        transport=FakeBytesTransport(b"{}"),
    )

    with pytest.raises(MassiveApiError, match="another host"):
        client.get_json("https://example.com/v3/reference/tickers?cursor=abc")
