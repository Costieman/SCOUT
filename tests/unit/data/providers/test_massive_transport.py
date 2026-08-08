from email.message import Message
from urllib.error import HTTPError

import pytest

import trade_scout.data.providers.massive_transport as massive_transport
from trade_scout.data.providers.massive import MassiveApiError
from trade_scout.data.providers.massive_transport import RetryingUrllibBytesTransport


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        return None

    def read(self) -> bytes:
        return self.payload


def test_transport_paces_successive_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([0.0, 2.0, 5.0])
    sleeps: list[float] = []
    transport = RetryingUrllibBytesTransport(
        min_interval_seconds=5.0,
        sleep=sleeps.append,
        monotonic=lambda: next(times),
    )
    monkeypatch.setattr(massive_transport, "urlopen", lambda request, timeout: FakeResponse(b"{}"))

    assert transport.get("https://api.massive.com/one", timeout=1.0) == b"{}"
    assert transport.get("https://api.massive.com/two", timeout=1.0) == b"{}"

    assert sleeps == [3.0]


def test_transport_retries_http_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    headers = Message()
    headers["Retry-After"] = "2"
    attempts = 0

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError(request.full_url, 429, "Too Many Requests", headers, None)
        return FakeResponse(b'{"status":"ok"}')

    sleeps: list[float] = []
    transport = RetryingUrllibBytesTransport(
        min_interval_seconds=0.0,
        sleep=sleeps.append,
        monotonic=lambda: 0.0,
    )
    monkeypatch.setattr(massive_transport, "urlopen", fake_urlopen)

    result = transport.get("https://api.massive.com/test", timeout=1.0)

    assert result == b'{"status":"ok"}'
    assert attempts == 2
    assert sleeps == [2.0]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_transport_retries_transient_server_errors(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    attempts = 0

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError(request.full_url, status, "Transient server error", Message(), None)
        return FakeResponse(b'{"status":"ok"}')

    sleeps: list[float] = []
    transport = RetryingUrllibBytesTransport(
        min_interval_seconds=0.0,
        base_backoff_seconds=3.0,
        sleep=sleeps.append,
        monotonic=lambda: 0.0,
    )
    monkeypatch.setattr(massive_transport, "urlopen", fake_urlopen)

    result = transport.get("https://api.massive.com/test", timeout=1.0)

    assert result == b'{"status":"ok"}'
    assert attempts == 2
    assert sleeps == [3.0]


def test_transport_does_not_retry_nontransient_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        raise HTTPError(request.full_url, 404, "Not Found", Message(), None)

    sleeps: list[float] = []
    transport = RetryingUrllibBytesTransport(
        min_interval_seconds=0.0,
        sleep=sleeps.append,
        monotonic=lambda: 0.0,
    )
    monkeypatch.setattr(massive_transport, "urlopen", fake_urlopen)

    with pytest.raises(MassiveApiError, match="Massive HTTP error 404"):
        transport.get("https://api.massive.com/test", timeout=1.0)

    assert attempts == 1
    assert sleeps == []


def test_transport_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        RetryingUrllibBytesTransport(min_interval_seconds=-1.0)
    with pytest.raises(ValueError):
        RetryingUrllibBytesTransport(max_attempts=0)
