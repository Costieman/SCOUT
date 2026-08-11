"""Stable contracts for versioned pattern state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import DatasetVersion, InstrumentId, QualityStatus


class PatternLifecycleState(StrEnum):
    """Lifecycle states defined by the Pattern & Event Engine specification."""

    NONE = "NONE"
    FORMING = "FORMING"
    QUALIFIED = "QUALIFIED"
    TRIGGER_READY = "TRIGGER_READY"
    INVALIDATED = "INVALIDATED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True, slots=True)
class StructuralBoundary:
    """One named point-in-time structural level attached to a pattern instance."""

    name: str
    value: float


@dataclass(frozen=True, slots=True)
class ResolvedPatternParameter:
    """One resolved parameter used to define a pattern instance."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class PatternState:
    """Vendor-independent, reproducible pattern-state record."""

    pattern_instance_id: str
    instrument_id: InstrumentId
    pattern_family: str
    pattern_version: str
    as_of_date: date
    state: PatternLifecycleState
    formation_start: date | None
    formation_end: date | None
    resolved_parameters: tuple[ResolvedPatternParameter, ...]
    structural_boundaries: tuple[StructuralBoundary, ...]
    feature_set_version: str
    dataset_version: DatasetVersion
    quality_status: QualityStatus
