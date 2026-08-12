"""Stable vendor-independent event contracts shared across research modules.

The event layer owns the definition of an event. Downstream outcome, risk, statistics,
validation, scanner, and alert modules may consume these records, but must not import a
pattern implementation in order to measure what happened after an event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import InstrumentId


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Minimum stable contract required by downstream post-event research.

    ``signal_index`` is retained as a deterministic daily-bar locator for the current
    implementation. The scientific identity of the event remains the immutable event ID,
    instrument, signal date, dataset version, and registered event-definition version.
    Pattern-specific geometry belongs in a pattern/event subtype or resolved metadata, not
    in downstream outcome logic.
    """

    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str
