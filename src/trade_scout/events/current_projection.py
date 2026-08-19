"""Latest-session projection for the canonical consolidation lifecycle/event pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import ResearchBar
from trade_scout.events.consolidation_pipeline import (
    ConsolidationEventConfig,
    IncrementalConsolidationPipeline,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig
from trade_scout.patterns.contracts import PatternLifecycleState


@dataclass(frozen=True, slots=True)
class CurrentPatternProjection:
    """Surface-friendly latest state without re-defining pattern or event semantics."""

    as_of_date: date
    status: str
    structural_state: PatternLifecycleState | None
    pattern_instance_id: str | None
    trigger_boundary: float | None
    distance_to_trigger_pct: float | None
    trend_qualified: bool | None
    breakout_volume_ratio: float | None
    latest_event_id: str | None
    message: str


def project_latest_consolidation_state(
    bars: tuple[ResearchBar, ...],
    config: ConsolidationBreakoutConfig,
) -> CurrentPatternProjection:
    """Replay the shared incremental pipeline and project only the latest observed session."""

    if not bars:
        raise ValueError("at least one research bar is required")

    event_config = ConsolidationEventConfig.from_legacy_config(config)
    engine = IncrementalConsolidationPipeline(config, event_config=event_config)
    latest_update = None
    for bar in bars:
        latest_update = engine.update(bar)
    if latest_update is None:  # pragma: no cover - guarded by non-empty bars above
        raise RuntimeError("latest consolidation update is unexpectedly absent")

    latest = bars[-1]
    volume_ratio = _volume_ratio(
        bars,
        signal_index=len(bars) - 1,
        lookback_sessions=event_config.volume_lookback_sessions,
    )

    if latest_update.event is not None:
        event = latest_update.event
        return CurrentPatternProjection(
            as_of_date=latest.trade_date,
            status="BREAKOUT",
            structural_state=PatternLifecycleState.CONSUMED,
            pattern_instance_id=event.pattern_instance_id,
            trigger_boundary=event.trigger_boundary,
            distance_to_trigger_pct=(event.trigger_boundary - latest.close)
            / event.trigger_boundary,
            trend_qualified=True,
            breakout_volume_ratio=volume_ratio,
            latest_event_id=event.event_id,
            message="Latest session generated a canonical breakout event from the active pattern.",
        )

    state = latest_update.pattern_states[-1] if latest_update.pattern_states else None
    if state is None:
        return CurrentPatternProjection(
            as_of_date=latest.trade_date,
            status="INACTIVE",
            structural_state=None,
            pattern_instance_id=None,
            trigger_boundary=None,
            distance_to_trigger_pct=None,
            trend_qualified=None,
            breakout_volume_ratio=volume_ratio,
            latest_event_id=None,
            message="No active or terminal consolidation state was emitted on the latest session.",
        )

    boundary = state.structural_boundaries.get("resistance")
    distance = None if boundary is None else (boundary - latest.close) / boundary
    reason = state.resolved_parameters.get("invalidation_reason")
    trend_ok = reason != "trend_context_failed"

    if state.state is PatternLifecycleState.INVALIDATED:
        if reason == "data_quality_or_eligibility":
            status = "QUALITY_BLOCKED"
            message = (
                "Latest session invalidated the pattern because quality or eligibility failed."
            )
        elif reason == "trend_context_failed":
            status = "TREND_FILTER_FAIL"
            message = "Latest session invalidated the pattern because the trend context failed."
        else:
            status = "INVALIDATED"
            message = f"Latest session invalidated the pattern: {reason or 'unspecified reason'}."
    elif (
        boundary is not None
        and latest.close > boundary
        and not _volume_confirmed(volume_ratio, event_config.min_breakout_volume_ratio)
    ):
        status = "VOLUME_FILTER_FAIL"
        message = "Price crossed resistance, but the configured breakout-volume gate was not met."
    elif state.state is PatternLifecycleState.TRIGGER_READY:
        status = "TRIGGER_READY"
        message = "The consolidation is active and close enough to its stored trigger boundary."
    else:
        status = "STRUCTURE_ACTIVE"
        message = "A qualified consolidation is active; no canonical breakout fired this session."

    return CurrentPatternProjection(
        as_of_date=latest.trade_date,
        status=status,
        structural_state=state.state,
        pattern_instance_id=state.pattern_instance_id,
        trigger_boundary=boundary,
        distance_to_trigger_pct=distance,
        trend_qualified=trend_ok,
        breakout_volume_ratio=volume_ratio,
        latest_event_id=None,
        message=message,
    )


def _volume_confirmed(observed: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return observed is not None and observed >= threshold


def _volume_ratio(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    lookback_sessions: int,
) -> float | None:
    if signal_index < lookback_sessions:
        return None
    trailing = bars[signal_index - lookback_sessions : signal_index]
    if any(item.volume < 0 for item in trailing) or bars[signal_index].volume < 0:
        return None
    average = sum(item.volume for item in trailing) / lookback_sessions
    if average <= 0:
        return None
    return bars[signal_index].volume / average
