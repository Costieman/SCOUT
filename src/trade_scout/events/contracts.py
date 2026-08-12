"""Stable vendor-independent event contracts shared across research modules.

The event layer owns the definition of an event. Downstream outcome, risk, statistics,
validation, scanner, and alert modules may consume these records, but must not import a
pattern implementation in order to measure what happened after an event.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from trade_scout.data.contracts import InstrumentId


class EventRecord(Protocol):
    """Structural contract required by downstream post-event research.

    Concrete event families may carry additional pattern-specific geometry and metadata.
    Downstream modules depend only on this shared surface, so measuring an outcome never
    requires importing or reinterpreting the pattern implementation that created the event.
    """

    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str
