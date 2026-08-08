"""Conservative HTTP pacing and retry behavior for the Massive provider adapter."""

from __future__ import annotations

import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from trade_scout.data.providers.massive import MassiveApiError


class RetryingUrllibBytesTransport:
    """Standard-library byte transport with explicit pacing and 429 retry handling."""

    def __init__(
        self,
        *,
        min_interval_seconds: float = 0.0,
        max_attempts: int = 6,
        base_backoff_seconds: float = 10.0,
        max_backoff_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if base_backoff_seconds <= 0 or max_backoff_seconds <= 0:
            raise ValueError("backoff seconds must be positive")
        self._min_interval_seconds = min_interval_seconds
        self._max_attempts = max_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._last_request_started: float | None = None

    def get(self, url: str, *, timeout: float) -> bytes:
        """Return bytes while pacing requests and retrying explicit rate-limit responses."""

        for attempt in range(self._max_attempts):
            self._pace()
            request = Request(url, headers={"Accept": "application/json"})
            try:
                with urlopen(request, timeout=timeout) as response:
                    return bytes(response.read())
            except HTTPError as exc:
                if exc.code == 429 and attempt + 1 < self._max_attempts:
                    self._sleep(self._retry_delay(exc, attempt))
                    continue
                raise MassiveApiError(f"Massive HTTP error {exc.code}") from exc
            except URLError as exc:
                raise MassiveApiError(f"Massive network error: {exc.reason}") from exc
        raise AssertionError("unreachable Massive retry loop")

    def _pace(self) -> None:
        now = self._monotonic()
        if self._last_request_started is not None:
            elapsed = now - self._last_request_started
            remaining = self._min_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_started = now

    def _retry_delay(self, error: HTTPError, attempt: int) -> float:
        retry_after = error.headers.get("Retry-After")
        parsed = _parse_retry_after(retry_after, wall_time=self._wall_time())
        if parsed is not None:
            return float(min(max(parsed, 0.0), self._max_backoff_seconds))
        exponential = self._base_backoff_seconds * (2**attempt)
        return min(exponential, self._max_backoff_seconds)


def _parse_retry_after(value: str | None, *, wall_time: float) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        pass
    try:
        retry_at = float(parsedate_to_datetime(stripped).timestamp())
    except (TypeError, ValueError, OverflowError):
        return None
    return retry_at - wall_time
