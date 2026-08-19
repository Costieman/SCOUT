"""Process-local read cache for iterative Strategy Builder research.

The Research Station is deliberately designed for repeated neighboring experiments against one
immutable canonical dataset. Re-reading and re-materializing the same canonical universe on every
button press adds latency without adding information. This adapter preserves the source contract and
only memoizes immutable/read-only results for the lifetime of the local research-workbench process.
No provider calls or analytical results are cached.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from pathlib import Path

from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.app.windowed_canonical_source import WindowedCanonicalUniverseResearchSource
from trade_scout.data.contracts import DailyBar, ResearchBar


class CachedWindowedCanonicalUniverseResearchSource(WindowedCanonicalUniverseResearchSource):
    """Reuse canonical source reads across neighboring interactive research runs."""

    __slots__ = (
        "_available_universes_cache",
        "_canonical_daily_bars_cache",
        "_research_series_cache",
        "_strategy_window_cache",
        "_strategy_window_cache_limit",
    )

    def __init__(
        self,
        *,
        canonical_root: Path,
        dataset_version: str,
        identity_candidate_path: Path,
        strategy_window_cache_limit: int = 8,
    ) -> None:
        if strategy_window_cache_limit < 1:
            raise ValueError("strategy_window_cache_limit must be positive")
        super().__init__(
            canonical_root=canonical_root,
            dataset_version=dataset_version,
            identity_candidate_path=identity_candidate_path,
        )
        self._available_universes_cache: tuple[UniverseOption, ...] | None = None
        self._canonical_daily_bars_cache: dict[str, tuple[DailyBar, ...]] = {}
        self._research_series_cache: dict[str, dict[str, tuple[ResearchBar, ...]]] = {}
        self._strategy_window_cache: OrderedDict[
            tuple[str, date, date, int], tuple[DailyBar, ...]
        ] = OrderedDict()
        self._strategy_window_cache_limit = strategy_window_cache_limit

    def available_universes(self) -> tuple[UniverseOption, ...]:
        cached = self._available_universes_cache
        if cached is None:
            cached = super().available_universes()
            self._available_universes_cache = cached
        return cached

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]:
        cached = self._research_series_cache.get(universe_id)
        if cached is None:
            cached = super().research_series(universe_id)
            self._research_series_cache[universe_id] = cached
        # The protocol exposes a dict, so return a shallow copy to keep the process cache read-only.
        return dict(cached)

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]:
        cached = self._canonical_daily_bars_cache.get(universe_id)
        if cached is None:
            cached = super().canonical_daily_bars(universe_id)
            self._canonical_daily_bars_cache[universe_id] = cached
        return cached

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        key = (universe_id, signal_start, signal_end, warmup_observations)
        cached = self._strategy_window_cache.get(key)
        if cached is not None:
            self._strategy_window_cache.move_to_end(key)
            return cached
        selected = super().strategy_builder_daily_bars(
            universe_id,
            signal_start=signal_start,
            signal_end=signal_end,
            warmup_observations=warmup_observations,
        )
        self._strategy_window_cache[key] = selected
        self._strategy_window_cache.move_to_end(key)
        while len(self._strategy_window_cache) > self._strategy_window_cache_limit:
            self._strategy_window_cache.popitem(last=False)
        return selected

    def clear_research_cache(self) -> None:
        """Drop all process-local read caches without touching canonical data."""

        self._available_universes_cache = None
        self._canonical_daily_bars_cache.clear()
        self._research_series_cache.clear()
        self._strategy_window_cache.clear()


__all__ = ["CachedWindowedCanonicalUniverseResearchSource"]
