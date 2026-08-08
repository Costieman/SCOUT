from __future__ import annotations

import json
from datetime import date

import pytest

from trade_scout.data.provider import DataFamily
from trade_scout.data.providers.sec_edgar import (
    SecEdgarAdapter,
    SecEdgarCapabilityError,
    SecEdgarClient,
    SecEdgarResponseError,
)


class FakeTransport:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, float]] = []

    def get(self, url: str, *, user_agent: str, timeout: float) -> bytes:
        self.calls.append((url, user_agent, timeout))
        return self._responses[url]


def _ticker_payload() -> bytes:
    return json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [320193, "Apple Inc.", "AAPL", "Nasdaq"],
                [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
            ],
        }
    ).encode()


def test_current_ticker_associations_map_without_claiming_identity() -> None:
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    transport = FakeTransport({url: _ticker_payload()})
    adapter = SecEdgarAdapter(
        SecEdgarClient("Trade Scout research@example.com", transport=transport)
    )

    instruments = adapter.get_instruments()

    assert [item.symbol for item in instruments] == ["AAPL", "GOOGL"]
    assert instruments[0].provider_instrument_id == "sec_edgar:cik:320193:ticker:AAPL"
    assert instruments[0].source_fields["cik"] == 320193
    assert "issuer-level" in str(instruments[0].source_fields["identity_warning"])
    assert transport.calls[0][1] == "Trade Scout research@example.com"


def test_capability_declaration_is_reference_only() -> None:
    adapter = SecEdgarAdapter(
        SecEdgarClient(
            "Trade Scout research@example.com",
            transport=FakeTransport({}),
        )
    )

    capabilities = adapter.describe_capabilities()

    assert capabilities.data_families == frozenset({DataFamily.INSTRUMENTS})
    assert capabilities.supports_delisted is False
    assert capabilities.supports_symbol_history is False
    assert capabilities.earliest_daily_bar_date is None
    assert any("CIK identifies" in item for item in capabilities.known_limitations)


def test_historical_as_of_request_fails_instead_of_back_projection() -> None:
    adapter = SecEdgarAdapter(
        SecEdgarClient(
            "Trade Scout research@example.com",
            transport=FakeTransport({}),
        )
    )

    with pytest.raises(SecEdgarCapabilityError, match="historical point-in-time"):
        adapter.get_instruments(as_of=date(2020, 1, 2))


def test_submissions_endpoint_uses_zero_padded_cik_and_returns_metadata() -> None:
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    transport = FakeTransport(
        {
            url: json.dumps(
                {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "formerNames": [],
                }
            ).encode()
        }
    )
    adapter = SecEdgarAdapter(
        SecEdgarClient("Trade Scout research@example.com", transport=transport)
    )

    metadata = adapter.get_issuer_metadata(320193)

    assert metadata["name"] == "Apple Inc."
    assert metadata["tickers"] == ["AAPL"]
    assert transport.calls[0][0] == url


def test_malformed_ticker_payload_fails_visibly() -> None:
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    malformed = json.dumps(
        {"fields": ["cik", "ticker"], "data": [[320193, "AAPL"]]}
    ).encode()
    adapter = SecEdgarAdapter(
        SecEdgarClient(
            "Trade Scout research@example.com",
            transport=FakeTransport({url: malformed}),
        )
    )

    with pytest.raises(SecEdgarResponseError, match="missing required columns"):
        adapter.get_instruments()


def test_empty_user_agent_is_rejected() -> None:
    with pytest.raises(ValueError, match="user agent"):
        SecEdgarClient("   ")
