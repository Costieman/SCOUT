import json
from collections.abc import Mapping
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation
from trade_scout.data.provider import CorporateActionRequest, DailyBarRequest, ProviderAdapter
from trade_scout.data.providers.tiingo import (
    TiingoAdapter,
    TiingoApiError,
    TiingoHttpClient,
    TiingoIdentityError,
    TiingoInstrumentLink,
    TiingoUnsupportedError,
)
from trade_scout.data.raw_store import Primitive


class FakeTiingoClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Primitive]]] = []

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> object:
        params = dict(parameters or {})
        self.calls.append((endpoint, params))
        if endpoint == "/api/test/":
            return {"message": "You successfully sent a request"}
        if endpoint == "/tiingo/daily/AAA/prices":
            return [
                {
                    "date": "2026-06-15T00:00:00.000Z",
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "volume": 1_000_000,
                    "adjOpen": 98.0,
                    "adjHigh": 99.96,
                    "adjLow": 97.02,
                    "adjClose": 98.98,
                    "adjVolume": 1_000_000,
                    "divCash": 0.25,
                    "splitFactor": 1.0,
                },
                {
                    "date": "2026-06-16T00:00:00.000Z",
                    "open": 51.0,
                    "high": 52.0,
                    "low": 50.0,
                    "close": 51.5,
                    "volume": 2_000_000,
                    "adjOpen": 51.0,
                    "adjHigh": 52.0,
                    "adjLow": 50.0,
                    "adjClose": 51.5,
                    "adjVolume": 2_000_000,
                    "divCash": 0.0,
                    "splitFactor": 2.0,
                },
            ]
        raise AssertionError(f"unexpected Tiingo request: {endpoint} {params}")


def _adapter() -> TiingoAdapter:
    return TiingoAdapter(
        FakeTiingoClient(),
        instrument_links=(
            TiingoInstrumentLink(
                query_symbol="AAA",
                provider_instrument_id="tiingo-perma-asset-1",
            ),
        ),
    )


def test_tiingo_adapter_satisfies_protocol_with_explicit_limitations() -> None:
    adapter = _adapter()

    assert isinstance(adapter, ProviderAdapter)
    capabilities = adapter.describe_capabilities()
    assert capabilities.adjustment_modes == frozenset({PriceRepresentation.RAW})
    assert capabilities.supports_delisted is True
    assert capabilities.supports_symbol_history is False
    assert any("dividend" in item for item in capabilities.known_limitations)


def test_daily_bars_keep_raw_ohlcv_and_do_not_mislabel_total_return_adjustment() -> None:
    adapter = _adapter()

    bars = adapter.get_daily_bars(
        DailyBarRequest(
            start=date(2026, 6, 15),
            end=date(2026, 6, 16),
            provider_symbols=("AAA",),
        )
    )

    assert len(bars) == 2
    first, second = bars
    assert first.provider_instrument_id == "tiingo-perma-asset-1"
    assert first.close == 101.0
    assert first.dividend_cash == 0.25
    assert first.adjusted_close is None
    assert second.split_factor is None
    assert second.volume == 2_000_000.0
    assert second.adjusted_open is None
    assert any("cumulative" in item for item in adapter.describe_capabilities().known_limitations)


def test_eod_split_and_dividend_fields_become_validation_actions() -> None:
    adapter = _adapter()

    actions = adapter.get_corporate_actions(
        CorporateActionRequest(
            start=date(2026, 6, 15),
            end=date(2026, 6, 16),
            provider_symbols=("AAA",),
        )
    )

    assert [(action.action_type, action.effective_date) for action in actions] == [
        (CorporateActionType.CASH_DIVIDEND, date(2026, 6, 15)),
        (CorporateActionType.SPLIT, date(2026, 6, 16)),
    ]
    assert all(action.provider_instrument_id == "tiingo-perma-asset-1" for action in actions)
    assert all(action.source_event_id is None for action in actions)


def test_unlinked_symbol_and_split_adjusted_request_fail_explicitly() -> None:
    adapter = _adapter()

    with pytest.raises(TiingoIdentityError):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 6, 15),
                end=date(2026, 6, 16),
                provider_symbols=("BBB",),
            )
        )

    with pytest.raises(TiingoUnsupportedError, match="dividends"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 6, 15),
                end=date(2026, 6, 16),
                provider_symbols=("AAA",),
                adjustment=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )


def test_security_master_and_symbol_history_fail_as_unsupported() -> None:
    adapter = _adapter()

    with pytest.raises(TiingoUnsupportedError, match="instrument enumeration"):
        adapter.get_instruments()
    with pytest.raises(TiingoUnsupportedError, match="symbol history"):
        adapter.get_symbol_history(provider_instrument_ids=("tiingo-perma-asset-1",))


def test_health_check_uses_tiingo_test_endpoint() -> None:
    client = FakeTiingoClient()
    adapter = TiingoAdapter(client, instrument_links=())

    health = adapter.health_check()

    assert health.status.value == "HEALTHY"
    assert client.calls == [("/api/test/", {})]


class FakeBytesTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        assert timeout > 0
        self.urls.append(url)
        self.headers.append(dict(headers))
        return self.payload


def test_http_client_keeps_token_in_authorization_header_not_url() -> None:
    transport = FakeBytesTransport(json.dumps([]).encode())
    client = TiingoHttpClient("secret-token", transport=transport)

    assert (
        client.get_json(
            "/tiingo/daily/AAA/prices",
            {"startDate": "2026-06-15", "endDate": "2026-06-16"},
        )
        == []
    )

    parsed = urlsplit(transport.urls[0])
    assert "token" not in {key.lower() for key in parse_qs(parsed.query)}
    assert transport.headers[0]["Authorization"] == "Token secret-token"


def test_http_client_refuses_non_tiingo_absolute_url() -> None:
    client = TiingoHttpClient("secret-token", transport=FakeBytesTransport(b"[]"))

    with pytest.raises(TiingoApiError, match="unexpected host"):
        client.get_json("https://example.com/tiingo/daily/AAA/prices")
