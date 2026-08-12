"""Stable contracts for objective pattern-state outputs.

Pattern detection owns structural market state. Event generation may consume these records,
but outcomes, risk, scanner, and presentation layers must not infer or rewrite pattern state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import InstrumentId, QualityStatus

PatternParameter = str | int | float | bool | None


class PatternLifecycleState(StrEnum):
    """Registered lifecycle states for a persistent technical pattern."""

    NONE = "NONE"
    FORMING = "FORMING"
    QUALIFIED = "QUALIFIED"
    TRIGGER_READY = "TRIGGER_READY"
    INVALIDATED = "INVALIDATED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True, slots=True)
class PatternState:
    """Vendor-independent snapshot of one registered pattern instance.

    Pattern identity is independent of any later outcome. ``resolved_parameters`` and
    ``structural_boundaries`` are immutable-by-convention mappings supplied by the detector;
    downstream consumers must treat them as read-only provenance rather than recalculate the
    pattern from market data.
    """

    pattern_instance_id: str
    instrument_id: InstrumentId
    pattern_family: str
    pattern_version: str
    as_of_date: date
    state: PatternLifecycleState
    formation_start: date
    formation_end: date
    resolved_parameters: Mapping[str, PatternParameter]
    structural_boundaries: Mapping[str, float]
    feature_set_version: str
    dataset_version: str
    quality_status: QualityStatus

    def __post_init__(self) -> None:
        if not self.pattern_instance_id:
            raise ValueError("pattern_instance_id must not be empty")
        if not self.pattern_family or not self.pattern_version:
            raise ValueError("pattern family and version must not be empty")
        if self.formation_start > self.formation_end:
            raise ValueError("formation_start must not be after formation_end")
        if self.formation_end > self.as_of_date:
            raise ValueError("formation interval cannot extend beyond as_of_date")
        if not self.feature_set_version or not self.dataset_version:
            raise ValueError("feature_set_version and dataset_version must not be empty")
