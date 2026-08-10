"""Deterministic review queue for A+B gaps and provider discrepancies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from trade_scout.data.composite_adjudication import (
    CompositeAdjudicationDecision,
    CompositeAdjudicationState,
    propose_composite_adjudication,
    record_composite_review,
)
from trade_scout.data.composite_evidence import CompositeEvidenceReport, CompositeEvidenceRow


class CompositeReviewKind(StrEnum):
    GAP = "GAP"
    DISCREPANCY = "DISCREPANCY"


@dataclass(frozen=True, slots=True)
class CompositeReviewQueueItem:
    """Provider-neutral work item for one non-corroborated instrument/session."""

    review_id: str
    kind: CompositeReviewKind
    instrument_id: str
    trade_date: str
    provider_a_id: str
    provider_b_id: str
    provider_a_present: bool
    provider_b_present: bool
    differing_fields: tuple[str, ...]
    proposed_state: CompositeAdjudicationState


@dataclass(frozen=True, slots=True)
class CompositeReviewResolution:
    """Explicit human/research resolution for one deterministic review item."""

    review_id: str
    final_state: CompositeAdjudicationState
    review_note: str

    def __post_init__(self) -> None:
        if self.final_state not in {
            CompositeAdjudicationState.PRIMARY_ACCEPTED,
            CompositeAdjudicationState.SECONDARY_ACCEPTED,
            CompositeAdjudicationState.REJECTED,
        }:
            raise ValueError("composite review resolution must select a final reviewed state")
        if not self.review_note.strip():
            raise ValueError("composite review resolution requires a non-empty audit note")


class CompositeReviewQueueError(ValueError):
    """Raised when a review batch is incomplete, duplicated, or does not match evidence."""


def build_composite_review_queue(
    report: CompositeEvidenceReport,
) -> tuple[CompositeReviewQueueItem, ...]:
    """Return only A+B rows that require explicit review before promotion."""

    items: list[CompositeReviewQueueItem] = []
    for row in report.rows:
        proposed = propose_composite_adjudication(row)
        if proposed.is_final:
            continue
        items.append(_queue_item(row, proposed.state))
    return tuple(items)


def adjudicate_composite_report(
    report: CompositeEvidenceReport,
    resolutions: tuple[CompositeReviewResolution, ...],
) -> tuple[CompositeAdjudicationDecision, ...]:
    """Produce a complete final decision set or fail without silently skipping review work."""

    queue = build_composite_review_queue(report)
    by_review_id = _resolution_map(resolutions)
    expected = {item.review_id for item in queue}
    supplied = set(by_review_id)
    missing = expected - supplied
    extra = supplied - expected
    if missing or extra:
        raise CompositeReviewQueueError(
            "composite review resolution coverage mismatch: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )

    queue_by_key = {(item.instrument_id, item.trade_date): item for item in queue}
    decisions: list[CompositeAdjudicationDecision] = []
    for row in report.rows:
        decision = propose_composite_adjudication(row)
        if decision.is_final:
            decisions.append(decision)
            continue
        key = (str(row.instrument_id), row.trade_date.isoformat())
        item = queue_by_key[key]
        resolution = by_review_id[item.review_id]
        decisions.append(
            record_composite_review(
                decision,
                state=resolution.final_state,
                review_note=resolution.review_note,
            )
        )
    return tuple(decisions)


def review_id_for_row(row: CompositeEvidenceRow) -> str:
    """Stable identifier derived from canonical identity, session, and observed A+B state."""

    payload = "|".join(
        (
            str(row.instrument_id),
            row.trade_date.isoformat(),
            row.provider_a_id,
            row.provider_b_id,
            row.state.value,
            ",".join(row.differing_fields),
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()[:24]


def _queue_item(
    row: CompositeEvidenceRow,
    proposed_state: CompositeAdjudicationState,
) -> CompositeReviewQueueItem:
    kind = (
        CompositeReviewKind.DISCREPANCY
        if row.requires_discrepancy_review
        else CompositeReviewKind.GAP
    )
    return CompositeReviewQueueItem(
        review_id=review_id_for_row(row),
        kind=kind,
        instrument_id=str(row.instrument_id),
        trade_date=row.trade_date.isoformat(),
        provider_a_id=row.provider_a_id,
        provider_b_id=row.provider_b_id,
        provider_a_present=row.provider_a_bar is not None,
        provider_b_present=row.provider_b_bar is not None,
        differing_fields=row.differing_fields,
        proposed_state=proposed_state,
    )


def _resolution_map(
    resolutions: tuple[CompositeReviewResolution, ...],
) -> dict[str, CompositeReviewResolution]:
    result: dict[str, CompositeReviewResolution] = {}
    for resolution in resolutions:
        if resolution.review_id in result:
            raise CompositeReviewQueueError(
                f"duplicate composite review resolution {resolution.review_id}"
            )
        result[resolution.review_id] = resolution
    return result
