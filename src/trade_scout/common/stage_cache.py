"""Deterministic bounded cache primitives for reusable research pipeline stages.

The cache is intentionally small and in-memory. It is an execution optimization, not a source of
truth: authoritative experiment manifests and canonical datasets remain unchanged. Cache identity is
explicitly derived from the stage name, stage-definition version, and only the dependencies that can
change that stage's output.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class StageFingerprint:
    """Immutable identity for one deterministic research-stage result."""

    stage: str
    version: str
    digest: str

    @classmethod
    def build(
        cls,
        *,
        stage: str,
        version: str,
        dependencies: Mapping[str, object],
    ) -> "StageFingerprint":
        """Build a stable fingerprint from explicitly declared stage dependencies."""

        resolved_stage = stage.strip()
        resolved_version = version.strip()
        if not resolved_stage:
            raise ValueError("stage fingerprint requires a non-empty stage name")
        if not resolved_version:
            raise ValueError("stage fingerprint requires a non-empty stage version")
        payload = {
            "stage": resolved_stage,
            "version": resolved_version,
            "dependencies": dependencies,
        }
        try:
            encoded = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("stage fingerprint dependencies must be JSON-serializable") from exc
        return cls(
            stage=resolved_stage,
            version=resolved_version,
            digest=sha256(encoded).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class StageCacheStats:
    """Small operator-facing cache telemetry snapshot."""

    hits: int
    misses: int
    stores: int
    evictions: int
    size: int
    max_entries: int


class BoundedStageCache(Generic[T]):
    """Thread-safe LRU cache keyed by deterministic stage fingerprints."""

    def __init__(self, *, max_entries: int = 32) -> None:
        if max_entries < 1:
            raise ValueError("stage cache max_entries must be positive")
        self._max_entries = max_entries
        self._items: OrderedDict[StageFingerprint, T] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._evictions = 0

    def get(self, fingerprint: StageFingerprint) -> T | None:
        """Return a cached value and refresh its LRU position when present."""

        with self._lock:
            try:
                value = self._items.pop(fingerprint)
            except KeyError:
                self._misses += 1
                return None
            self._items[fingerprint] = value
            self._hits += 1
            return value

    def put(self, fingerprint: StageFingerprint, value: T) -> None:
        """Store one value, evicting the least-recently-used entry if necessary."""

        with self._lock:
            if fingerprint in self._items:
                self._items.pop(fingerprint)
            self._items[fingerprint] = value
            self._stores += 1
            while len(self._items) > self._max_entries:
                self._items.popitem(last=False)
                self._evictions += 1

    def get_or_compute(self, fingerprint: StageFingerprint, compute: Callable[[], T]) -> T:
        """Reuse an existing deterministic result or compute and store it once missing."""

        cached = self.get(fingerprint)
        if cached is not None:
            return cached
        value = compute()
        self.put(fingerprint, value)
        return value

    def clear(self) -> None:
        """Drop disposable cached values without altering telemetry counters."""

        with self._lock:
            self._items.clear()

    def stats(self) -> StageCacheStats:
        """Return immutable cache telemetry for profiling and regression tests."""

        with self._lock:
            return StageCacheStats(
                hits=self._hits,
                misses=self._misses,
                stores=self._stores,
                evictions=self._evictions,
                size=len(self._items),
                max_entries=self._max_entries,
            )


__all__ = ["BoundedStageCache", "StageCacheStats", "StageFingerprint"]
