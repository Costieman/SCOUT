"""Deterministic pattern-bar aggregation with daily execution mapping.

Pattern timeframe and holding horizon are deliberately separate. Pattern bars may be daily,
non-overlapping 2-session or 3-session bars, or calendar-week bars. Signals are always mapped
back to the final underlying daily session so downstream outcomes can enter at the next daily
open and measure holding horizons in daily trading sessions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from typing import Any

from trade_scout.data.contracts import PriceRepresentation, QualityStatus, ResearchBar


class PatternTimeframe(StrEnum):
    """Pattern-bar construction supported by the exploratory research workbench."""

    DAILY = "daily"
    TWO_SESSION = "2_session"
    THREE_SESSION = "3_session"
    WEEKLY = "weekly"


@dataclass(frozen=True, slots=True)
class PatternSeriesFrame:
    """Aggregated pattern bars plus their exact source-daily index mapping."""

    timeframe: PatternTimeframe
    bars: tuple[ResearchBar, ...]
    source_start_indices: tuple[int, ...]
    source_end_indices: tuple[int, ...]
    anchor_description: str

    def __post_init__(self) -> None:
        count = len(self.bars)
        if len(self.source_start_indices) != count or len(self.source_end_indices) != count:
            raise ValueError("pattern-bar mappings must align one-to-one with pattern bars")
        if any(
            start > end
            for start, end in zip(
                self.source_start_indices,
                self.source_end_indices,
                strict=True,
            )
        ):
            raise ValueError("pattern-bar source start cannot be after source end")


def build_pattern_frames(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    timeframe: PatternTimeframe,
) -> dict[str, PatternSeriesFrame]:
    """Build aligned pattern bars for each instrument from the shared market-session calendar."""

    if not series_by_symbol:
        raise ValueError("pattern timeframe aggregation requires instrument series")
    _validate_source_series(series_by_symbol)
    market_sessions = tuple(
        sorted({bar.trade_date for bars in series_by_symbol.values() for bar in bars})
    )
    blocks, anchor = _market_blocks(market_sessions, timeframe)
    result: dict[str, PatternSeriesFrame] = {}
    for symbol, bars in sorted(series_by_symbol.items()):
        by_date = {bar.trade_date: (index, bar) for index, bar in enumerate(bars)}
        pattern_bars: list[ResearchBar] = []
        source_starts: list[int] = []
        source_ends: list[int] = []
        for block in blocks:
            matched = tuple(by_date.get(session) for session in block)
            if any(item is None for item in matched):
                continue
            resolved = tuple(item for item in matched if item is not None)
            indices = tuple(item[0] for item in resolved)
            source_bars = tuple(item[1] for item in resolved)
            pattern_bars.append(_aggregate_block(source_bars))
            source_starts.append(indices[0])
            source_ends.append(indices[-1])
        result[symbol] = PatternSeriesFrame(
            timeframe=timeframe,
            bars=tuple(pattern_bars),
            source_start_indices=tuple(source_starts),
            source_end_indices=tuple(source_ends),
            anchor_description=anchor,
        )
    return result


def remap_breakout_events_to_daily(
    events: tuple[Any, ...],
    frame: PatternSeriesFrame,
) -> tuple[Any, ...]:
    """Map dataclass event signal indices to underlying daily indices for outcome measurement.

    The pattern layer intentionally does not depend on a concrete downstream event family. Any
    immutable dataclass event with ``signal_index``, ``event_id`` and
    ``event_definition_version`` fields can be remapped here.
    """

    remapped: list[Any] = []
    for event in events:
        if event.signal_index < 0 or event.signal_index >= len(frame.source_end_indices):
            raise ValueError("pattern event signal index is outside the source mapping")
        daily_index = frame.source_end_indices[event.signal_index]
        if frame.timeframe is PatternTimeframe.DAILY:
            remapped.append(replace(event, signal_index=daily_index))
            continue
        remapped.append(
            replace(
                event,
                signal_index=daily_index,
                event_id=f"{event.event_id}:pattern_timeframe={frame.timeframe.value}",
                event_definition_version="consolidation-close-breakout-timeframe-v0.2",
            )
        )
    return tuple(remapped)


def source_index_for_pattern_index(frame: PatternSeriesFrame, pattern_index: int) -> int:
    """Return the final underlying daily index for one pattern-bar index."""

    if pattern_index < 0 or pattern_index >= len(frame.source_end_indices):
        raise IndexError("pattern index outside source mapping")
    return frame.source_end_indices[pattern_index]


def _market_blocks(
    market_sessions: tuple[date, ...],
    timeframe: PatternTimeframe,
) -> tuple[tuple[tuple[date, ...], ...], str]:
    if not market_sessions:
        raise ValueError("market-session calendar must not be empty")
    if timeframe is PatternTimeframe.DAILY:
        return tuple(
            (session,) for session in market_sessions
        ), "one source session per pattern bar"
    if timeframe in {PatternTimeframe.TWO_SESSION, PatternTimeframe.THREE_SESSION}:
        size = 2 if timeframe is PatternTimeframe.TWO_SESSION else 3
        blocks = tuple(
            market_sessions[start : start + size]
            for start in range(0, len(market_sessions), size)
            if len(market_sessions[start : start + size]) == size
        )
        return (
            blocks,
            f"non-overlapping {size}-session blocks anchored to the first market session "
            "in the dataset",
        )

    grouped: list[list[date]] = []
    current_key: tuple[int, int] | None = None
    for session in market_sessions:
        iso = session.isocalendar()
        key = (iso.year, iso.week)
        if key != current_key:
            grouped.append([])
            current_key = key
        grouped[-1].append(session)
    if grouped and market_sessions[-1].weekday() != 4:
        grouped = grouped[:-1]
    return (
        tuple(tuple(group) for group in grouped if group),
        "ISO calendar weeks; final partial week is excluded unless the latest session is Friday",
    )


def _aggregate_block(bars: tuple[ResearchBar, ...]) -> ResearchBar:
    if not bars:
        raise ValueError("cannot aggregate an empty pattern-bar block")
    instruments = {bar.instrument_id for bar in bars}
    versions = {bar.dataset_version for bar in bars}
    representations = {bar.price_representation for bar in bars}
    if len(instruments) != 1 or len(versions) != 1 or len(representations) != 1:
        raise ValueError(
            "pattern-bar block cannot mix instruments, datasets, or price representations"
        )
    dates = tuple(bar.trade_date for bar in bars)
    if tuple(sorted(dates)) != dates or len(set(dates)) != len(dates):
        raise ValueError("pattern-bar source dates must be unique and increasing")
    return ResearchBar(
        instrument_id=bars[0].instrument_id,
        trade_date=bars[-1].trade_date,
        open=bars[0].open,
        high=max(bar.high for bar in bars),
        low=min(bar.low for bar in bars),
        close=bars[-1].close,
        volume=sum(bar.volume for bar in bars),
        eligibility=all(bar.eligibility for bar in bars),
        quality_status=_worst_quality(tuple(bar.quality_status for bar in bars)),
        dataset_version=bars[0].dataset_version,
        price_representation=bars[0].price_representation,
    )


def _worst_quality(states: tuple[QualityStatus, ...]) -> QualityStatus:
    severity = {
        QualityStatus.PASS: 0,
        QualityStatus.WARN: 1,
        QualityStatus.QUARANTINE: 2,
        QualityStatus.REJECT: 3,
    }
    return max(states, key=lambda state: severity[state])


def _validate_source_series(series_by_symbol: Mapping[str, tuple[ResearchBar, ...]]) -> None:
    versions: set[str] = set()
    for raw_symbol, bars in series_by_symbol.items():
        if not raw_symbol.strip() or not bars:
            raise ValueError("pattern timeframe source symbols and series must be non-empty")
        if len({bar.instrument_id for bar in bars}) != 1:
            raise ValueError(f"pattern timeframe source {raw_symbol} mixes instruments")
        if len({bar.dataset_version for bar in bars}) != 1:
            raise ValueError(f"pattern timeframe source {raw_symbol} mixes dataset versions")
        if len({bar.price_representation for bar in bars}) != 1:
            raise ValueError(f"pattern timeframe source {raw_symbol} mixes price representations")
        dates = tuple(bar.trade_date for bar in bars)
        if tuple(sorted(dates)) != dates or len(set(dates)) != len(dates):
            raise ValueError(f"pattern timeframe source {raw_symbol} must be date-increasing")
        versions.add(str(bars[0].dataset_version))
        if bars[0].price_representation is not PriceRepresentation.SPLIT_ADJUSTED:
            raise ValueError("pattern timeframe research requires split-adjusted source bars")
    if len(versions) != 1:
        raise ValueError("pattern timeframe aggregation cannot mix canonical dataset versions")


__all__ = [
    "PatternSeriesFrame",
    "PatternTimeframe",
    "build_pattern_frames",
    "remap_breakout_events_to_daily",
    "source_index_for_pattern_index",
]
