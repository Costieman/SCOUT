from __future__ import annotations

from dataclasses import dataclass

import pytest

from trade_scout.data.providers.eodhd import EodhdApiError, EodhdBytesTransport
from trade_scout.data.providers.eodhd_resilience import (
    EodhdAuthenticationError,
    EodhdRateLimitError,
    EodhdRetryingBytesTransport,
    EodhdRetryPolicy,
    EodhdTransientError,
)


@dataclass
class SequenceTransport(EodhdBytesTransport):
    outcomes: list[bytes | Exception]

    def get(self, url: str, *, timeout: float) -> bytes:
        assert url.startswith("https://")
        assert timeout > 0
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_transient_failure_retries_with_bounded_exponential_delay() -> None:
    delays: list[float] = []
    transport = EodhdRetryingBytesTransport(
        SequenceTransport([EodhdTransientError("temporary"), b"ok"]),
        policy=EodhdRetryPolicy(
            max_attempts=3,
            base_delay_seconds=2.0,
            max_delay_seconds=10.0,
            jitter_fraction=0.0,
        ),
        sleeper=delays.append,
        random_unit=lambda: 0.5,
    )

    assert transport.get("https://eodhd.com/api/test", timeout=1.0) == b"ok"
    assert delays == [2.0]


def test_rate_limit_retry_after_is_honored_and_capped() -> None:
    delays: list[float] = []
    transport = EodhdRetryingBytesTransport(
        SequenceTransport(
            [
                EodhdRateLimitError("rate", retry_after_seconds=60.0),
                b"ok",
            ]
        ),
        policy=EodhdRetryPolicy(
            max_attempts=2,
            base_delay_seconds=1.0,
            max_delay_seconds=5.0,
            jitter_fraction=0.0,
        ),
        sleeper=delays.append,
        random_unit=lambda: 0.5,
    )

    assert transport.get("https://eodhd.com/api/test", timeout=1.0) == b"ok"
    assert delays == [5.0]


def test_authentication_and_permanent_api_errors_are_not_retried() -> None:
    for error in (EodhdAuthenticationError("bad key"), EodhdApiError("bad request")):
        delays: list[float] = []
        transport = EodhdRetryingBytesTransport(
            SequenceTransport([error, b"unexpected"]),
            sleeper=delays.append,
        )

        with pytest.raises(type(error)):
            transport.get("https://eodhd.com/api/test", timeout=1.0)

        assert delays == []


def test_retry_exhaustion_raises_last_classified_failure() -> None:
    transport = EodhdRetryingBytesTransport(
        SequenceTransport(
            [
                EodhdTransientError("one"),
                EodhdTransientError("two"),
            ]
        ),
        policy=EodhdRetryPolicy(
            max_attempts=2,
            base_delay_seconds=0.0,
            max_delay_seconds=0.0,
            jitter_fraction=0.0,
        ),
        sleeper=lambda _: None,
        random_unit=lambda: 0.5,
    )

    with pytest.raises(EodhdTransientError, match="two"):
        transport.get("https://eodhd.com/api/test", timeout=1.0)


def test_invalid_random_source_fails_visibly() -> None:
    transport = EodhdRetryingBytesTransport(
        SequenceTransport([EodhdTransientError("temporary"), b"ok"]),
        policy=EodhdRetryPolicy(max_attempts=2),
        sleeper=lambda _: None,
        random_unit=lambda: 2.0,
    )

    with pytest.raises(ValueError, match="random source"):
        transport.get("https://eodhd.com/api/test", timeout=1.0)
