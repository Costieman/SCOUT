"""Stable vendor-independent research-data serving contract."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
    to_research_bar,
)

EligibilityKey = tuple[InstrumentId, date]
_RESEARCH_ELIGIBLE_QUALITY_STATES = frozenset({QualityStatus.PASS, QualityStatus.WARN})


class ResearchDataContractError(ValueError):
    """Base error for invalid or ambiguous research-data requests."""


class MissingEligibilityError(ResearchDataContractError):
    """Raised when a requested instrument/session lacks point-in-time universe state."""


class ResearchDatasetVersionError(ResearchDataContractError):
    """Raised when supplied bars do not belong to the requested canonical dataset version."""


class DuplicateResearchBarError(ResearchDataContractError):
    """Raised when canonical input contains multiple bars for one instrument/session."""


@dataclass(frozen=True, slots=True)
class ResearchDataRequest:
    """Explicit data-layer request consumed by downstream research modules."""

    dataset_version: DatasetVersion
    start: date
    end: date
    price_representation: PriceRepresentation
    allowed_quality_states: frozenset[QualityStatus]

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ResearchDataContractError("research-data end date must be on or after start date")
        if not self.allowed_quality_states:
            raise ResearchDataContractError("at least one research quality state must be allowed")
        unsupported = self.allowed_quality_states - _RESEARCH_ELIGIBLE_QUALITY_STATES
        if unsupported:
            names = ", ".join(sorted(str(status) for status in unsupported))
            raise ResearchDataContractError(
                f"research serving cannot enable blocked quality states: {names}"
            )


def serve_research_bars(
    bars: Iterable[DailyBar],
    *,
    eligibility_by_key: Mapping[EligibilityKey, bool],
    request: ResearchDataRequest,
) -> tuple[ResearchBar, ...]:
    """Materialize deterministic ResearchBar records without provider-native dependencies."""

    selected: list[ResearchBar] = []
    seen: set[EligibilityKey] = set()

    for bar in bars:
        if not request.start <= bar.trade_date <= request.end:
            continue
        if bar.dataset_version != request.dataset_version:
            raise ResearchDatasetVersionError(
                f"bar {bar.instrument_id}:{bar.trade_date} uses dataset {bar.dataset_version}; "
                f"requested {request.dataset_version}"
            )

        key = (bar.instrument_id, bar.trade_date)
        if key in seen:
            raise DuplicateResearchBarError(
                f"duplicate research bar for {bar.instrument_id} on {bar.trade_date}"
            )
        seen.add(key)

        if bar.quality_status not in _RESEARCH_ELIGIBLE_QUALITY_STATES:
            raise ResearchDataContractError(
                f"blocked quality state {bar.quality_status} reached research serving for "
                f"{bar.instrument_id}:{bar.trade_date}"
            )
        if bar.quality_status not in request.allowed_quality_states:
            continue

        try:
            eligibility = eligibility_by_key[key]
        except KeyError as exc:
            raise MissingEligibilityError(
                f"point-in-time eligibility is missing for {bar.instrument_id} on {bar.trade_date}"
            ) from exc

        selected.append(
            to_research_bar(
                bar,
                representation=request.price_representation,
                eligibility=eligibility,
            )
        )

    return tuple(sorted(selected, key=lambda row: (str(row.instrument_id), row.trade_date)))
