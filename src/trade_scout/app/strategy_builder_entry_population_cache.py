"""Dependency-aware cache for frozen Strategy Builder entry populations.

The entry population is upstream of outcome and exit-policy evaluation. Its cache identity therefore
contains only data/window/entry-definition dependencies. Stop, target, slippage, commission, and
other post-entry settings are intentionally absent so neighboring exit-policy experiments can reuse
the exact same frozen event population.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from trade_scout.common.stage_cache import BoundedStageCache, StageCacheStats, StageFingerprint
from trade_scout.events.contracts import EventRecord

_ENTRY_POPULATION_STAGE_VERSION = "strategy-builder-frozen-entry-population-v1"
_ENTRY_POPULATION_CACHE: BoundedStageCache["FrozenEntryPopulation"] = BoundedStageCache(
    max_entries=8
)


@dataclass(frozen=True, slots=True)
class FrozenEntryPopulation:
    """Immutable event population produced before any exit policy is evaluated."""

    events_by_instrument: tuple[tuple[str, tuple[EventRecord, ...]], ...]
    event_count: int
    entry_definition_version: str

    def as_mapping(self) -> dict[str, tuple[EventRecord, ...]]:
        """Return a fresh mapping so callers cannot mutate the cached container."""

        return dict(self.events_by_instrument)


def frozen_entry_population_fingerprint(
    *,
    dataset_version: str,
    universe_id: str,
    analysis_start: str,
    analysis_end: str,
    entry_family: str,
    entry_definition_version: str,
    canonical_scope: object,
    entry_parameters: Mapping[str, object],
) -> StageFingerprint:
    """Fingerprint only dependencies that can alter entry-event membership."""

    return StageFingerprint.build(
        stage="frozen_entry_population",
        version=_ENTRY_POPULATION_STAGE_VERSION,
        dependencies={
            "dataset_version": dataset_version,
            "universe_id": universe_id,
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "entry_family": entry_family,
            "entry_definition_version": entry_definition_version,
            "canonical_scope": canonical_scope,
            "entry_parameters": dict(entry_parameters),
        },
    )


def get_or_compute_frozen_entry_population(
    fingerprint: StageFingerprint,
    compute: Callable[[], FrozenEntryPopulation],
) -> tuple[FrozenEntryPopulation, bool]:
    """Return one frozen population and whether it came from the bounded cache."""

    cached = _ENTRY_POPULATION_CACHE.get(fingerprint)
    if cached is not None:
        return cached, True
    population = compute()
    if population.event_count < 0:
        raise ValueError("frozen entry population event_count cannot be negative")
    observed = sum(len(events) for _, events in population.events_by_instrument)
    if observed != population.event_count:
        raise ValueError(
            "frozen entry population event_count does not match instrument event membership"
        )
    _ENTRY_POPULATION_CACHE.put(fingerprint, population)
    return population, False


def reset_frozen_entry_population_cache() -> None:
    """Clear disposable cached populations for deterministic tests or operator reset."""

    _ENTRY_POPULATION_CACHE.clear()


def frozen_entry_population_cache_stats() -> StageCacheStats:
    """Expose cache telemetry without making cache contents authoritative."""

    return _ENTRY_POPULATION_CACHE.stats()


__all__ = [
    "FrozenEntryPopulation",
    "frozen_entry_population_cache_stats",
    "frozen_entry_population_fingerprint",
    "get_or_compute_frozen_entry_population",
    "reset_frozen_entry_population_cache",
]
