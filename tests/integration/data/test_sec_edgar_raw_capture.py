from __future__ import annotations

import json
from collections.abc import Mapping

from trade_scout.data.providers.sec_edgar import SecEdgarClient
from trade_scout.data.raw_store import Primitive


class FakeTransport:
    def __init__(self, response: bytes) -> None:
        self.response = response

    def get(self, url: str, *, user_agent: str, timeout: float) -> bytes:
        del url, user_agent, timeout
        return self.response


class RecordingCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, Mapping[str, Primitive], str]] = []

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
        media_type: str,
    ) -> None:
        self.calls.append((payload, endpoint, request_parameters, media_type))


def test_ticker_response_is_captured_before_normalization() -> None:
    payload = json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
        }
    ).encode()
    capture = RecordingCapture()
    client = SecEdgarClient(
        "Trade Scout research@example.com",
        transport=FakeTransport(payload),
        raw_capture=capture,
    )

    associations = client.get_ticker_associations()

    assert associations[0].ticker == "AAPL"
    assert capture.calls == [
        (
            payload,
            "/files/company_tickers_exchange.json",
            {"dataset": "company_tickers_exchange"},
            "application/json",
        )
    ]


def test_submissions_response_is_captured_with_padded_cik() -> None:
    payload = b'{"cik":"0000320193","name":"Apple Inc."}'
    capture = RecordingCapture()
    client = SecEdgarClient(
        "Trade Scout research@example.com",
        transport=FakeTransport(payload),
        raw_capture=capture,
    )

    metadata = client.get_submissions(320193)

    assert metadata["name"] == "Apple Inc."
    assert capture.calls == [
        (
            payload,
            "/submissions/CIK.json",
            {"cik": "0000320193"},
            "application/json",
        )
    ]
