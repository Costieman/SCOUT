"""Pure consolidation pattern-state emission.

This module evaluates whether a prior window forms a qualified consolidation and emits the
canonical PatternState consumed by the event layer. It does not create breakout events or
inspect forward outcomes.
"""

from __future__ import annotations

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    _range_pct,
    _trend_qualified,
)
from trade_scout.patterns.contracts import PatternLifecycleState, PatternState

PATTERN_VERSION = "consolidation-range-v0.1"
FEATURE_SET_VERSION = "legacy-inline-trend-v0.2"


def qualified_pattern_at(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    config: ConsolidationBreakoutConfig,
) -> PatternState | None:
    """Emit a qualified prior-window consolidation for one candidate signal bar.

    The signal bar is used only as the knowledge timestamp and for the point-in-time trend
    condition. Pattern geometry is calculated exclusively from the preceding ``duration`` bars.
    A later event generator may then decide whether the signal bar crosses the stored boundary.
    """

    if not bars:
        raise ValueError("at least one research bar is required")
    if signal_index < config.duration or signal_index >= len(bars):
        raise ValueError("signal_index must have a complete prior consolidation window")

    signal = bars[signal_index]
    base = bars[signal_index - config.duration : signal_index]
    if any(not item.eligibility or item.quality_status is not QualityStatus.PASS for item in base):
        return None
    if not signal.eligibility or signal.quality_status is not QualityStatus.PASS:
        return None

    instrument_ids = {item.instrument_id for item in (*base, signal)}
    dataset_versions = {str(item.dataset_version) for item in (*base, signal)}
    if len(instrument_ids) != 1:
        raise ValueError("pattern evaluation requires one instrument")
    if len(dataset_versions) != 1:
        raise ValueError("pattern evaluation requires one dataset version")

    resistance = max(item.high for item in base)
    support = min(item.low for item in base)
    range_pct = _range_pct(resistance, support)
    if range_pct > config.max_range_pct:
        return None
    if not _trend_qualified(bars, signal_index, config.trend_filter):
        return None

    formation_start = base[0].trade_date
    formation_end = base[-1].trade_date
    pattern_instance_id = (
        f"{signal.instrument_id}:{PATTERN_VERSION}:"
        f"{formation_start.isoformat()}:{formation_end.isoformat()}:"
        f"{config.duration}:{config.max_range_pct:.6f}:{config.trend_filter.value}"
    )
    return PatternState(
        pattern_instance_id=pattern_instance_id,
        instrument_id=signal.instrument_id,
        pattern_family="consolidation",
        pattern_version=PATTERN_VERSION,
        as_of_date=signal.trade_date,
        state=PatternLifecycleState.QUALIFIED,
        formation_start=formation_start,
        formation_end=formation_end,
        resolved_parameters={
            "duration": config.duration,
            "max_range_pct": config.max_range_pct,
            "trend_filter": config.trend_filter.value,
            "base_range_pct": range_pct,
        },
        structural_boundaries={"resistance": resistance, "support": support},
        feature_set_version=FEATURE_SET_VERSION,
        dataset_version=str(signal.dataset_version),
        quality_status=QualityStatus.PASS,
    )


def detect_qualified_patterns(
    bars: tuple[ResearchBar, ...],
    config: ConsolidationBreakoutConfig,
) -> tuple[PatternState, ...]:
    """Evaluate all signal dates without creating or deduplicating events."""

    if not bars:
        raise ValueError("at least one research bar is required")
    states: list[PatternState] = []
    for signal_index in range(config.duration, len(bars)):
        state = qualified_pattern_at(bars, signal_index=signal_index, config=config)
        if state is not None:
            states.append(state)
    return tuple(states)
