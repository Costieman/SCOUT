"""Window-aware canonical source for interactive Strategy Builder research."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from trade_scout.app.universe_research_service import (
    CanonicalUniverseResearchSource,
    UniverseResearchError,
)
from trade_scout.data.canonical_window import CanonicalDailyBarWindowReader
from trade_scout.data.contracts import DailyBar, DatasetVersion, QualityStatus


class WindowedCanonicalUniverseResearchSource(CanonicalUniverseResearchSource):
    """Canonical source that can fetch an exact signal window plus indicator warm-up."""

    __slots__ = ("_window_reader",)
    _window_reader: CanonicalDailyBarWindowReader

    def __init__(
        self,
        *,
        canonical_root: Path,
        dataset_version: str,
        identity_candidate_path: Path,
    ) -> None:
        super().__init__(
            canonical_root=canonical_root,
            dataset_version=dataset_version,
            identity_candidate_path=identity_candidate_path,
        )
        object.__setattr__(
            self,
            "_window_reader",
            CanonicalDailyBarWindowReader(canonical_root, DatasetVersion(dataset_version)),
        )

    def strategy_builder_latest_trade_date(self, universe_id: str) -> date:
        self._reviewed_symbol_by_instrument(universe_id)
        return self._window_reader.latest_trade_date()

    def strategy_builder_dataset_record_count(self, universe_id: str) -> int:
        self._reviewed_symbol_by_instrument(universe_id)
        return self._window_reader.manifest_record_count()

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        symbol_by_instrument = self._reviewed_symbol_by_instrument(universe_id)
        selected = self._window_reader.load_window(
            instrument_ids=tuple(symbol_by_instrument),
            signal_start=signal_start,
            signal_end=signal_end,
            warmup_observations=warmup_observations,
        )
        if not selected:
            raise UniverseResearchError(
                "requested Strategy Builder window contains no fully reviewed canonical rows"
            )
        non_pass = tuple(item for item in selected if item.quality_status is not QualityStatus.PASS)
        if non_pass:
            first = non_pass[0]
            symbol = symbol_by_instrument.get(str(first.instrument_id), str(first.instrument_id))
            raise UniverseResearchError(f"canonical series {symbol} contains non-PASS quality rows")
        return selected


__all__ = ["WindowedCanonicalUniverseResearchSource"]
