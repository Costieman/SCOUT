from __future__ import annotations

from collections.abc import Mapping

import pytest

from trade_scout.data.providers.alpha_vantage import (
    AlphaVantageHttpClient,
    AlphaVantageResponseError,
)
from trade_scout.data.raw_store import Primitive


class FakeTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get(self, url: str, *, timeout: float) -> bytes:
        del url, timeout
        return self.payload


class FakeCapture:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.media_types: list[str] = []
        self.parameters: list[dict[str, Primitive]] = []

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
        media_type: str,
    ) -> None:
        assert endpoint == "/query"
        self.payloads.append(payload)
        self.media_types.append(media_type)
        self.parameters.append(dict(request_parameters))


def test_unexpected_json_is_preserved_before_validation_failure() -> None:
    payload = b'{"message":"unexpected provider response"}'
    capture = FakeCapture()
    client = AlphaVantageHttpClient(
        "secret",
        transport=FakeTransport(payload),
        raw_capture=capture,
    )

    with pytest.raises(AlphaVantageResponseError, match="keys: message"):
        client.get_csv({"function": "LISTING_STATUS", "state": "active"})

    assert capture.payloads == [payload]
    assert capture.media_types == ["application/json"]
    assert capture.parameters == [{"function": "LISTING_STATUS", "state": "active"}]


def test_csv_response_is_preserved_with_csv_media_type() -> None:
    payload = b"symbol,name\nIBM,International Business Machines\n"
    capture = FakeCapture()
    client = AlphaVantageHttpClient(
        "secret",
        transport=FakeTransport(payload),
        raw_capture=capture,
    )

    assert client.get_csv({"function": "LISTING_STATUS", "state": "active"}) == payload
    assert capture.payloads == [payload]
    assert capture.media_types == ["text/csv"]
