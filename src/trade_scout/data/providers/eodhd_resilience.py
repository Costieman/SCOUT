"""Classified, bounded retry behavior for EODHD transport failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from random import random
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from trade_scout.data.providers.eodhd import EodhdApiError, EodhdBytesTransport


class EodhdAuthenticationError(EodhdApiError):
    """Raised for authentication/authorization failures that must not be retried."""


class EodhdRateLimitError(EodhdApiError):
    """Raised when EODHD explicitly throttles a request."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class EodhdTransientError(EodhdApiError):
    """Raised for bounded-retry network or service failures."""


@dataclass(frozen=True, slots=True)
class EodhdRetryPolicy:
    """Explicit retry policy; attempt count includes the initial request."""

    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter_fraction: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("EODHD retry max_attempts must be positive")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("EODHD retry delays must be non-negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("EODHD max retry delay cannot be below base delay")
        if not 0 <= self.jitter_fraction <= 1:
            raise ValueError("EODHD jitter_fraction must be between zero and one")


_DEFAULT_RETRY_POLICY = EodhdRetryPolicy()


class EodhdClassifyingUrllibTransport:
    """HTTPS transport that separates auth, throttling, transient, and permanent failures."""

    def get(self, url: str, *, timeout: float) -> bytes:
        try:
            with urlopen(
                Request(url, headers={"Accept": "application/json"}), timeout=timeout
            ) as response:
                return bytes(response.read())
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise EodhdAuthenticationError(
                    f"EODHD authentication HTTP error {exc.code}"
                ) from exc
            if exc.code == 429:
                raise EodhdRateLimitError(
                    "EODHD rate-limit HTTP error 429",
                    retry_after_seconds=_retry_after(exc),
                ) from exc
            if exc.code in {408, 425, 500, 502, 503, 504}:
                raise EodhdTransientError(f"EODHD transient HTTP error {exc.code}") from exc
            raise EodhdApiError(f"EODHD HTTP error {exc.code}") from exc
        except URLError as exc:
            raise EodhdTransientError(f"EODHD network error: {exc.reason}") from exc


class EodhdRetryingBytesTransport:
    """Retry only classified transient/throttling failures using bounded backoff and jitter."""

    def __init__(
        self,
        transport: EodhdBytesTransport,
        *,
        policy: EodhdRetryPolicy = _DEFAULT_RETRY_POLICY,
        sleeper: Callable[[float], None] = sleep,
        random_unit: Callable[[], float] = random,
    ) -> None:
        self._transport = transport
        self._policy = policy
        self._sleeper = sleeper
        self._random_unit = random_unit

    def get(self, url: str, *, timeout: float) -> bytes:
        last_error: EodhdApiError | None = None
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                return self._transport.get(url, timeout=timeout)
            except (EodhdRateLimitError, EodhdTransientError) as exc:
                last_error = exc
                if attempt >= self._policy.max_attempts:
                    raise
                self._sleeper(self._delay_seconds(attempt, exc))
        if last_error is not None:
            raise last_error
        raise RuntimeError("EODHD retry transport reached an impossible state")

    def _delay_seconds(self, attempt: int, error: EodhdApiError) -> float:
        if isinstance(error, EodhdRateLimitError) and error.retry_after_seconds is not None:
            base = min(error.retry_after_seconds, self._policy.max_delay_seconds)
        else:
            base = min(
                self._policy.base_delay_seconds * (2 ** (attempt - 1)),
                self._policy.max_delay_seconds,
            )
        jitter_span = base * self._policy.jitter_fraction
        random_value = self._random_unit()
        if not 0 <= random_value <= 1:
            raise ValueError("EODHD retry random source must return a value between zero and one")
        multiplier = (
            1 - self._policy.jitter_fraction + (2 * self._policy.jitter_fraction * random_value)
        )
        return min(base * multiplier, self._policy.max_delay_seconds + jitter_span)


def _retry_after(error: HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers is not None else None
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
