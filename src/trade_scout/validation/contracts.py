"""Typed contracts for time-ordered research validation.

The validation layer plans and records how fixed research definitions are challenged. It does not
change pattern, event, outcome, risk, or ranking definitions and does not infer production
eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from itertools import pairwise


class ValidationRole(StrEnum):
    """Role assigned to a time interval before any outcomes are inspected."""

    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"


@dataclass(frozen=True, slots=True)
class DateInterval:
    """Inclusive calendar-date interval used by a validation plan."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("date interval end must be on or after start")

    def overlaps(self, other: DateInterval) -> bool:
        """Return whether this interval shares any date with another interval."""

        return self.start <= other.end and other.start <= self.end


@dataclass(frozen=True, slots=True)
class ValidationSegment:
    """One immutable development, validation, or final-holdout segment."""

    segment_id: str
    role: ValidationRole
    interval: DateInterval

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id must be non-empty")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    """One time-ordered train/test fold with no future-data overlap."""

    fold_id: str
    development: DateInterval
    validation: DateInterval

    def __post_init__(self) -> None:
        if not self.fold_id.strip():
            raise ValueError("fold_id must be non-empty")
        if self.development.end >= self.validation.start:
            raise ValueError("walk-forward development must end before validation begins")


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    """Frozen validation design attached to a confirmatory research definition."""

    plan_id: str
    segments: tuple[ValidationSegment, ...]
    walk_forward_folds: tuple[WalkForwardFold, ...] = ()
    primary_outcome: str | None = None
    comparator_id: str | None = None
    robustness_checks: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        if not self.segments:
            raise ValueError("validation plan must contain at least one segment")
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("validation segment IDs must be unique")
        fold_ids = [fold.fold_id for fold in self.walk_forward_folds]
        if len(fold_ids) != len(set(fold_ids)):
            raise ValueError("walk-forward fold IDs must be unique")
        ordered = sorted(self.segments, key=lambda segment: segment.interval.start)
        for previous, current in pairwise(ordered):
            if previous.interval.overlaps(current.interval):
                raise ValueError("validation segments must not overlap")
        holdouts = [segment for segment in ordered if segment.role is ValidationRole.HOLDOUT]
        if len(holdouts) > 1:
            raise ValueError("validation plan may contain at most one final holdout segment")
        if holdouts and holdouts[0] is not ordered[-1]:
            raise ValueError("final holdout must be the chronologically last segment")
        if any(not check.strip() for check in self.robustness_checks):
            raise ValueError("robustness check names must be non-empty")
        if any(not note.strip() for note in self.notes):
            raise ValueError("validation notes must be non-empty")


@dataclass(frozen=True, slots=True)
class SampleAccounting:
    """Transparent raw and dependence-aware sample metadata for one result cell."""

    raw_event_count: int
    unique_instrument_count: int
    effective_sample_size: float | None = None
    cluster_count: int | None = None
    exclusions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.raw_event_count < 0 or self.unique_instrument_count < 0:
            raise ValueError("sample counts must be non-negative")
        if self.unique_instrument_count > self.raw_event_count:
            raise ValueError("unique instruments cannot exceed raw event count")
        if self.effective_sample_size is not None:
            if self.effective_sample_size < 0:
                raise ValueError("effective_sample_size must be non-negative")
            if self.effective_sample_size > self.raw_event_count:
                raise ValueError("effective_sample_size cannot exceed raw event count")
        if self.cluster_count is not None and self.cluster_count < 0:
            raise ValueError("cluster_count must be non-negative")
        if any(not exclusion.strip() for exclusion in self.exclusions):
            raise ValueError("sample exclusion descriptions must be non-empty")
