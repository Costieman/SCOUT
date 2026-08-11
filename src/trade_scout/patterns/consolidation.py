"""Point-in-time consolidation state detection.

The detector deliberately measures structure only. It does not inspect forward outcomes, apply
stop logic, or decide whether a detected structure is profitable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.patterns.contracts import (
    PatternLifecycleState,
    PatternState,
    ResolvedPatternParameter,
    StructuralBoundary,
)


@dataclass(frozen=True, slots=True)
class ConsolidationDefinition:
    """Resolved Version 1 consolidation definition."""

    duration_sessions: int = 20
    max_range_pct: float = 0.12
    trigger_ready_distance_pct: float = 0.02
    pattern_family: str = "consolidation"
    pattern_version: str = "consolidation-v0.1"
    feature_set_version: str = "canonical-bars-only-v0.1"

    def __post_init__(self) -> None:
        if self.duration_sessions < 2:
            raise ValueError("duration_sessions must be at least 2")
        if not 0 < self.max_range_pct <= 1:
            raise ValueError("max_range_pct must be in (0, 1]")
        if not 0 <= self.trigger_ready_distance_pct <= 1:
            raise ValueError("trigger_ready_distance_pct must be in [0, 1]")


def detect_consolidation_states(
    bars: tuple[ResearchBar, ...],
    definition: ConsolidationDefinition,
) -> tuple[PatternState, ...]:
    """Return one deterministic point-in-time pattern state per input session."""

    _validate_bars(bars)
    states: list[PatternState] = []
    active_instance_id: str | None = None
    active_formation_start = None
    prior_active = False

    parameters = (
        ResolvedPatternParameter("duration_sessions", str(definition.duration_sessions)),
        ResolvedPatternParameter("max_range_pct", f"{definition.max_range_pct:.12g}"),
        ResolvedPatternParameter(
            "trigger_ready_distance_pct", f"{definition.trigger_ready_distance_pct:.12g}"
        ),
    )

    for index, bar in enumerate(bars):
        if index + 1 < definition.duration_sessions:
            states.append(
                _state(
                    bar=bar,
                    definition=definition,
                    state=PatternLifecycleState.FORMING,
                    pattern_instance_id=_forming_id(bar, definition),
                    formation_start=bars[0].trade_date,
                    formation_end=bar.trade_date,
                    parameters=parameters,
                    boundaries=(),
                )
            )
            prior_active = False
            continue

        window = bars[index - definition.duration_sessions + 1 : index + 1]
        quality_ok = all(
            item.eligibility and item.quality_status is QualityStatus.PASS for item in window
        )
        high = max(item.high for item in window)
        low = min(item.low for item in window)
        range_pct = (high - low) / low
        qualifies = quality_ok and range_pct <= definition.max_range_pct

        if not qualifies:
            state = PatternLifecycleState.INVALIDATED if prior_active else PatternLifecycleState.NONE
            states.append(
                _state(
                    bar=bar,
                    definition=definition,
                    state=state,
                    pattern_instance_id=active_instance_id or _none_id(bar, definition),
                    formation_start=active_formation_start if prior_active else None,
                    formation_end=bar.trade_date if prior_active else None,
                    parameters=parameters,
                    boundaries=(
                        StructuralBoundary("support", low),
                        StructuralBoundary("resistance", high),
                    ),
                )
            )
            active_instance_id = None
            active_formation_start = None
            prior_active = False
            continue

        formation_start = window[0].trade_date
        instance_id = _qualified_id(bar.instrument_id, formation_start, definition)
        distance = max(0.0, (high - bar.close) / high)
        lifecycle = (
            PatternLifecycleState.TRIGGER_READY
            if distance <= definition.trigger_ready_distance_pct
            else PatternLifecycleState.QUALIFIED
        )
        active_instance_id = instance_id
        active_formation_start = formation_start
        prior_active = True
        states.append(
            _state(
                bar=bar,
                definition=definition,
                state=lifecycle,
                pattern_instance_id=instance_id,
                formation_start=formation_start,
                formation_end=bar.trade_date,
                parameters=parameters,
                boundaries=(
                    StructuralBoundary("support", low),
                    StructuralBoundary("resistance", high),
                ),
            )
        )

    return tuple(states)


def _state(
    *,
    bar: ResearchBar,
    definition: ConsolidationDefinition,
    state: PatternLifecycleState,
    pattern_instance_id: str,
    formation_start: object,
    formation_end: object,
    parameters: tuple[ResolvedPatternParameter, ...],
    boundaries: tuple[StructuralBoundary, ...],
) -> PatternState:
    return PatternState(
        pattern_instance_id=pattern_instance_id,
        instrument_id=bar.instrument_id,
        pattern_family=definition.pattern_family,
        pattern_version=definition.pattern_version,
        as_of_date=bar.trade_date,
        state=state,
        formation_start=formation_start,  # type: ignore[arg-type]
        formation_end=formation_end,  # type: ignore[arg-type]
        resolved_parameters=parameters,
        structural_boundaries=boundaries,
        feature_set_version=definition.feature_set_version,
        dataset_version=bar.dataset_version,
        quality_status=bar.quality_status,
    )


def _stable_id(prefix: str, payload: dict[str, str]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"


def _qualified_id(instrument_id: str, formation_start: object, definition: ConsolidationDefinition) -> str:
    return _stable_id(
        "pat",
        {
            "instrument_id": str(instrument_id),
            "pattern_version": definition.pattern_version,
            "formation_start": str(formation_start),
            "duration_sessions": str(definition.duration_sessions),
            "max_range_pct": f"{definition.max_range_pct:.12g}",
        },
    )


def _forming_id(bar: ResearchBar, definition: ConsolidationDefinition) -> str:
    return _stable_id(
        "forming",
        {
            "instrument_id": str(bar.instrument_id),
            "pattern_version": definition.pattern_version,
            "as_of_date": bar.trade_date.isoformat(),
        },
    )


def _none_id(bar: ResearchBar, definition: ConsolidationDefinition) -> str:
    return _stable_id(
        "none",
        {
            "instrument_id": str(bar.instrument_id),
            "pattern_version": definition.pattern_version,
            "as_of_date": bar.trade_date.isoformat(),
        },
    )


def _validate_bars(bars: tuple[ResearchBar, ...]) -> None:
    if not bars:
        raise ValueError("at least one research bar is required")
    if len({bar.instrument_id for bar in bars}) != 1:
        raise ValueError("pattern detection requires one instrument")
    if len({bar.dataset_version for bar in bars}) != 1:
        raise ValueError("pattern detection requires one dataset version")
    dates = tuple(bar.trade_date for bar in bars)
    if tuple(sorted(dates)) != dates or len(set(dates)) != len(dates):
        raise ValueError("research bars must be unique and date-increasing")
    if any(min(bar.open, bar.high, bar.low, bar.close) <= 0 for bar in bars):
        raise ValueError("research prices must be positive")
