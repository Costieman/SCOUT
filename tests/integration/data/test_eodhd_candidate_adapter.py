from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation, SecurityType
from trade_scout.data.provider import CorporateActionRequest, DailyBarRequest, DataFamily
from trade_scout.data.providers.eodhd import (
    EodhdAdapter,
    EodhdHttpClient,
    EodhdInstrumentLink,
    EodhdRawStoreCapture,
    EodhdResponseError,
    EodhdUnsupportedError,
)
from trade_scout.data.raw_store import RawBatchStore


class FixtureClient:
    def __init__(self, responses: Mapping[tuple[str, tuple[tuple[str, object], ...]], object]) -> None:
        self.responses = dict(responses)

    def get_json(self, endpoint: str, parameters: Mapping[str, object] | None = None) -> object:
        key = (endpoint, tuple(sorted((parameters or {}).items())))
        return self.responses[key]


class CaptureTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, *, timeout: float) -> bytes:
        assert timeout > 0
        self.urls.append(url)
        return self.payload


def _key(endpoint: str, **parameters: object) -> tuple[str, tuple[tuple[str, object], ...]]:
    return endpoint, tuple(sorted(parameters.items()))


def test_instruments_prefer_isin_and_flag_symbol_fallback() -> None:
    client = FixtureClient(
        {
            _key("/api/exchange-symbol-list/US", delisted=0): [
                {
                    "Code": "AAPL",
                    "Name": "Apple Inc",
                    "Country": "USA",
                    "Exchange": "NASDAQ",
                    "Currency": "USD",
                    "Type": "Common Stock",
                    "Isin": "US0378331005",
                },
                {
                    "Code": "NOISIN",
                    "Name": "No Isin Corp",
                    "Exchange": "NYSE",
                    "Currency": "USD",
                    "Type": "Common Stock",
                    "Isin": None,
                },
            ],
            _key("/api/exchange-symbol-list/US", delisted=1): [
                {
                    "Code": "OLD",
                    "Name": "Old Corp",
                    "Exchange": "NASDAQ",
                    "Currency": "USD",
                    "Type": "Common Stock",
                    "Isin": "US0000000001",
                }
            ],
        }
    )

    instruments = EodhdAdapter(client).get_instruments()

    apple = next(item for item in instruments if item.symbol == "AAPL.US")
    fallback = next(item for item in instruments if item.symbol == "NOISIN.US")
    old = next(item for item in instruments if item.symbol == "OLD.US")
    assert apple.provider_instrument_id == "eodhd:isin:US0378331005"
    assert apple.security_type is SecurityType.COMMON_STOCK
    assert apple.active is True
    assert apple.source_fields["identity_quality"] == "ISIN"
    assert fallback.provider_instrument_id == "eodhd:symbol:NOISIN.US"
    assert fallback.source_fields["identity_quality"] == "PROVISIONAL_SYMBOL"
    assert old.active is False


def test_historical_as_of_is_rejected_instead_of_back_projecting_current_inventory() -> None:
    with pytest.raises(EodhdUnsupportedError, match="must not be back-projected"):
        EodhdAdapter(FixtureClient({})).get_instruments(as_of=date(2018, 1, 2))


def test_daily_bars_require_explicit_identity_and_remain_raw() -> None:
    response = [
        {
            "date": "2026-01-02",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "adjusted_close": 10.4,
            "volume": 1234,
        }
    ]
    client = FixtureClient(
        {
            _key(
                "/api/eod/AAPL.US",
                **{"from": "2026-01-02", "to": "2026-01-02", "period": "d"},
            ): response
        }
    )
    adapter = EodhdAdapter(
        client,
        instrument_links=(
            EodhdInstrumentLink("AAPL.US", "eodhd:isin:US0378331005"),
        ),
    )
    request = DailyBarRequest(
        start=date(2026, 1, 2),
        end=date(2026, 1, 2),
        provider_symbols=("AAPL.US",),
        adjustment=PriceRepresentation.RAW,
    )

    bars = adapter.get_daily_bars(request)

    assert len(bars) == 1
    assert bars[0].provider_instrument_id == "eodhd:isin:US0378331005"
    assert bars[0].close == 10.5
    assert bars[0].split_factor is None
    assert bars[0].adjusted_close is None


def test_adjusted_daily_bars_are_not_relabelled_as_split_adjusted() -> None:
    adapter = EodhdAdapter(
        FixtureClient({}),
        instrument_links=(EodhdInstrumentLink("AAPL.US", "eodhd:isin:US0378331005"),),
    )
    with pytest.raises(EodhdUnsupportedError, match="adjusted_close is not relabelled"):
        adapter.get_daily_bars(
            DailyBarRequest(
                start=date(2026, 1, 2),
                end=date(2026, 1, 3),
                provider_symbols=("AAPL.US",),
                adjustment=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )


def test_splits_and_dividends_are_preserved_as_provider_actions() -> None:
    client = FixtureClient(
        {
            _key(
                "/api/splits/AAPL.US",
                **{"from": "2025-01-01", "to": "2025-12-31"},
            ): [{"date": "2025-06-01", "split": "4.000000/1.000000"}],
            _key(
                "/api/div/AAPL.US",
                **{"from": "2025-01-01", "to": "2025-12-31"},
            ): [{"date": "2025-08-01", "value": 0.25, "currency": "USD"}],
        }
    )
    adapter = EodhdAdapter(
        client,
        instrument_links=(EodhdInstrumentLink("AAPL.US", "eodhd:isin:US0378331005"),),
    )

    actions = adapter.get_corporate_actions(
        CorporateActionRequest(
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            provider_symbols=("AAPL.US",),
        )
    )

    assert [action.action_type for action in actions] == [
        CorporateActionType.SPLIT,
        CorporateActionType.CASH_DIVIDEND,
    ]
    assert all(action.provider_instrument_id == "eodhd:isin:US0378331005" for action in actions)


def test_capabilities_keep_symbol_history_unaccepted() -> None:
    capabilities = EodhdAdapter(FixtureClient({})).describe_capabilities()

    assert DataFamily.DAILY_BARS in capabilities.data_families
    assert DataFamily.STATUS_DELISTINGS in capabilities.data_families
    assert DataFamily.CORPORATE_ACTIONS in capabilities.data_families
    assert capabilities.supports_delisted is True
    assert capabilities.supports_symbol_history is False
    assert capabilities.adjustment_modes == frozenset({PriceRepresentation.RAW})


def test_http_client_keeps_api_token_out_of_raw_manifest(tmp_path: Path) -> None:
    transport = CaptureTransport(b"[]")
    store = RawBatchStore(tmp_path / "raw")
    client = EodhdHttpClient(
        "super-secret-token",
        transport=transport,
        raw_capture=EodhdRawStoreCapture(store),
    )

    assert client.get_json("/api/eod/AAPL.US", {"from": "2026-01-01"}) == []

    parsed = urlsplit(transport.urls[0])
    wire = parse_qs(parsed.query)
    assert wire["api_token"] == ["super-secret-token"]
    manifests = list((tmp_path / "raw").rglob("manifest.json"))
    assert len(manifests) == 1
    manifest_text = manifests[0].read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert "super-secret-token" not in manifest_text
    assert manifest["request_parameters"] == {"from": "2026-01-01"}


def test_invalid_json_fails_after_raw_capture(tmp_path: Path) -> None:
    transport = CaptureTransport(b"not-json")
    store = RawBatchStore(tmp_path / "raw")
    client = EodhdHttpClient(
        "token",
        transport=transport,
        raw_capture=EodhdRawStoreCapture(store),
    )

    with pytest.raises(EodhdResponseError, match="invalid JSON"):
        client.get_json("/api/eod/AAPL.US")

    payloads = list((tmp_path / "raw").rglob("payload.bin"))
    assert len(payloads) == 1
    assert payloads[0].read_bytes() == b"not-json"
