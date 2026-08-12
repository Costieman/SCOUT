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
    """Read-only structural contract required by downstream post-event research.

    Concrete event families may carry additional pattern-specific geometry and metadata.
    Downstream modules depend only on this shared surface, so measuring an outcome never
    requires importing or reinterpreting the pattern implementation that created the event.
    """

    @property
    def event_id(self) -> str: ...

    @property
    def instrument_id(self) -> InstrumentId: ...

    @property
    def signal_date(self) -> date: ...

    @property
    def signal_index(self) -> int: ...

    @property
    def dataset_version(self) -> str: ...

    @property
    def event_definition_version(self) -> str: ...
