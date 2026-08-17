"""Operator-facing registry for entry/setup families available to the strategy builder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EntryFamily(StrEnum):
    """Entry/setup families exposed by the first strategy-builder slice."""

    FEATURE_EXPRESSION = "feature_expression"
    CONSOLIDATION_BREAKOUT = "consolidation_breakout"


@dataclass(frozen=True, slots=True)
class EntryStrategyOption:
    """Stable application metadata for one registered entry family."""

    family: EntryFamily
    label: str
    description: str
    definition_version: str


_OPTIONS = (
    EntryStrategyOption(
        family=EntryFamily.FEATURE_EXPRESSION,
        label="Feature expression",
        description=(
            "Point-in-time boolean/arithmetic expression over registered market-analysis features, "
            "with optional cross-sectional ranking and per-session selection limits."
        ),
        definition_version="feature-expression-strategy-signal-v0.1",
    ),
    EntryStrategyOption(
        family=EntryFamily.CONSOLIDATION_BREAKOUT,
        label="Consolidation breakout",
        description=(
            "Close-confirmed breakout from a bounded prior range using the existing deterministic "
            "consolidation detector and optional trend/volume filters."
        ),
        definition_version="consolidation-close-breakout-v0.2",
    ),
)


def available_entry_strategies() -> tuple[EntryStrategyOption, ...]:
    """Return the deterministic registered entry/setup catalog."""

    return _OPTIONS


def entry_strategy_option(family: EntryFamily) -> EntryStrategyOption:
    """Resolve one registered family or fail closed."""

    for option in _OPTIONS:
        if option.family is family:
            return option
    raise ValueError(f"unregistered entry family {family!r}")


__all__ = [
    "EntryFamily",
    "EntryStrategyOption",
    "available_entry_strategies",
    "entry_strategy_option",
]
