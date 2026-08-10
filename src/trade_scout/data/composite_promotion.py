"""Materialize reviewed A+B decisions while retaining source-row provenance.

Canonical Trade Scout rows remain provider-independent at the dataset boundary. The selected
source provider is retained in a separate immutable provenance record so mixed Alpha Vantage /
Stooq datasets do not erase which provider supplied each accepted observation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from trade_scout.data.composite_adjudication import (
    CompositeAdjudicationDecision,
    CompositeAdjudicationState,
    InvalidCompositeAdjudicationError,
    selected_provider_bar,
)
from trade_scout.data.composite_evidence import CompositeCoverageState
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentRecord
from trade_scout.data.normalization import NormalizationIssue, normalize_provider_daily_bars

COMPOSITE_CANONICAL_PROVIDER_ID = "trade_scout_composite"


@dataclass(frozen=True, slots=True)
class CompositeRowProvenance:
    """Auditable source selection for one reviewed instrument/session."""

    instrument_id: str
    trade_date: str
    included: bool
    canonical_provider_id: str
    selected_source_provider_id: str | None
    selected_source_provider_instrument_id: str | None
    evidence_state: CompositeCoverageState
    adjudication_state: CompositeAdjudicationState
    review_note: str | None
    corroborating_provider_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompositeCanonicalizationResult:
    """Canonical bars plus complete row-level provenance and normalization failures."""

    bars: tuple[DailyBar, ...]
    provenance: tuple[CompositeRowProvenance, ...]
    normalization_issues: tuple[NormalizationIssue, ...]


class CompositeCanonicalizationError(ValueError):
    """Raised when reviewed evidence cannot be deterministically materialized."""


def canonicalize_composite_decisions(
    decisions: tuple[CompositeAdjudicationDecision, ...],
    *,
    instruments: tuple[InstrumentRecord, ...],
    dataset_version: DatasetVersion,
) -> CompositeCanonicalizationResult:
    """Convert final A+B decisions into canonical rows without losing source provenance.

    Review-required decisions are rejected rather than skipped. Rejected decisions remain in the
    provenance ledger but do not produce a canonical bar. Accepted provider rows pass through the
    normal provider-neutral normalization gate before their canonical ``provider_id`` is relabelled
    to the composite dataset identity. The original provider identity is retained in provenance.
    """

    ordered = tuple(
        sorted(
            decisions,
            key=lambda item: (
                str(item.evidence.instrument_id),
                item.evidence.trade_date,
            ),
        )
    )
    _validate_unique_sessions(ordered)

    bars: list[DailyBar] = []
    provenance: list[CompositeRowProvenance] = []
    issues: list[NormalizationIssue] = []

    for decision in ordered:
        if not decision.is_final:
            raise CompositeCanonicalizationError(
                "composite canonicalization requires every decision to be final"
            )

        evidence = decision.evidence
        corroborators = _corroborating_provider_ids(decision)
        if decision.state is CompositeAdjudicationState.REJECTED:
            provenance.append(
                CompositeRowProvenance(
                    instrument_id=str(evidence.instrument_id),
                    trade_date=evidence.trade_date.isoformat(),
                    included=False,
                    canonical_provider_id=COMPOSITE_CANONICAL_PROVIDER_ID,
                    selected_source_provider_id=None,
                    selected_source_provider_instrument_id=None,
                    evidence_state=evidence.state,
                    adjudication_state=decision.state,
                    review_note=decision.review_note,
                    corroborating_provider_ids=corroborators,
                )
            )
            continue

        try:
            selected = selected_provider_bar(decision)
        except InvalidCompositeAdjudicationError as exc:
            raise CompositeCanonicalizationError(str(exc)) from exc

        normalized = normalize_provider_daily_bars(
            (selected,),
            instruments=instruments,
            dataset_version=dataset_version,
        )
        issues.extend(normalized.normalization_issues)
        if len(normalized.bars) != 1:
            provenance.append(
                CompositeRowProvenance(
                    instrument_id=str(evidence.instrument_id),
                    trade_date=evidence.trade_date.isoformat(),
                    included=False,
                    canonical_provider_id=COMPOSITE_CANONICAL_PROVIDER_ID,
                    selected_source_provider_id=selected.provider_id,
                    selected_source_provider_instrument_id=selected.provider_instrument_id,
                    evidence_state=evidence.state,
                    adjudication_state=decision.state,
                    review_note=decision.review_note,
                    corroborating_provider_ids=corroborators,
                )
            )
            continue

        bar = normalized.bars[0]
        if bar.instrument_id != evidence.instrument_id or bar.trade_date != evidence.trade_date:
            raise CompositeCanonicalizationError(
                "normalized source observation does not match reviewed instrument/session identity"
            )
        bars.append(replace(bar, provider_id=COMPOSITE_CANONICAL_PROVIDER_ID))
        provenance.append(
            CompositeRowProvenance(
                instrument_id=str(evidence.instrument_id),
                trade_date=evidence.trade_date.isoformat(),
                included=True,
                canonical_provider_id=COMPOSITE_CANONICAL_PROVIDER_ID,
                selected_source_provider_id=selected.provider_id,
                selected_source_provider_instrument_id=selected.provider_instrument_id,
                evidence_state=evidence.state,
                adjudication_state=decision.state,
                review_note=decision.review_note,
                corroborating_provider_ids=corroborators,
            )
        )

    return CompositeCanonicalizationResult(
        bars=tuple(bars),
        provenance=tuple(provenance),
        normalization_issues=tuple(issues),
    )


def _validate_unique_sessions(decisions: tuple[CompositeAdjudicationDecision, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for decision in decisions:
        key = (
            str(decision.evidence.instrument_id),
            decision.evidence.trade_date.isoformat(),
        )
        if key in seen:
            raise CompositeCanonicalizationError(
                f"duplicate composite decision for instrument/session {key[0]} {key[1]}"
            )
        seen.add(key)


def _corroborating_provider_ids(
    decision: CompositeAdjudicationDecision,
) -> tuple[str, ...]:
    evidence = decision.evidence
    if evidence.state is CompositeCoverageState.BOTH_AGREE:
        return (evidence.provider_a_id, evidence.provider_b_id)
    if evidence.state is CompositeCoverageState.A_ONLY:
        return (evidence.provider_a_id,)
    if evidence.state is CompositeCoverageState.B_ONLY:
        return (evidence.provider_b_id,)
    return ()
