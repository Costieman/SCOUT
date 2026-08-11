"""Stable contracts for timestamped market events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from trade_scout.data.contracts import DatasetVersion, InstrumentId, QualityStatus
from trade_scout.patterns.contracts import ResolvedPatternParameter


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Immutable event contract consumed by downstream outcome and risk modules."""

    event_id: str
    instrument_id: InstrumentId
    event_type: str
    event_version: str
    pattern_instance_id: str
    signal_date: date
    knowledge_time: datetime | None
    earliest_execution_time: datetime | None
    trigger_value: float
    trigger_boundary: float
    resolved_parameters: tuple[ResolvedPatternParameter, ...]
    event_family_id: str
    feature_set_version: str
    dataset_version: DatasetVersion
    quality_status: QualityStatus
