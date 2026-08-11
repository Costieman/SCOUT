"""Classify targeted historical coverage-edge evidence without filling provider gaps."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from trade_scout.data.composite_evidence import CompositeCoverageState, CompositeEvidenceReport


class HistoricalEdgeStatus(StrEnum):
    """Evidence states for one reviewed initial-history gap."""

    SECONDARY_CONFIRMS_PRIMARY_GAP = "SECONDARY_CONFIRMS_PRIMARY_GAP"
    PRIMARY_COVERAGE_CHANGED = "PRIMARY_COVERAGE_CHANGED"
    ANCHOR_DISAGREEMENT = "ANCHOR_DISAGREEMENT"
    INCONCLUSIVE_SECONDARY_NONOBSERVATION = "INCONCLUSIVE_SECONDARY_NONOBSERVATION"
    INCONCLUSIVE_ANCHOR_MISSING = "INCONCLUSIVE_ANCHOR_MISSING"


def classify_initial_history_gap(
    evidence: CompositeEvidenceReport,
    *,
    expected_gap_sessions: tuple[date, ...],
    anchor_date: date,
) -> HistoricalEdgeStatus:
    """Interpret A-primary/B-secondary evidence for a reviewed initial coverage gap.

    A is the provider with the known initial coverage gap and B is the independent validator. A
    confirmed gap requires every reviewed gap session to be B-only and the overlap anchor to agree.
    Any A observation on a reviewed gap date means the primary provider's coverage changed and must
    be re-profiled rather than relying on stale evidence.
    """

    if not expected_gap_sessions:
        raise ValueError("expected_gap_sessions must not be empty")
    if anchor_date in expected_gap_sessions:
        raise ValueError("anchor_date must be outside the reviewed gap sessions")
    if len(set(expected_gap_sessions)) != len(expected_gap_sessions):
        raise ValueError("expected_gap_sessions must not contain duplicate dates")

    by_date = {row.trade_date: row for row in evidence.rows}
    if len(by_date) != len(evidence.rows):
        raise ValueError("historical edge evidence contains duplicate dates")

    gap_rows = tuple(by_date.get(day) for day in expected_gap_sessions)
    if any(
        row is not None
        and row.state
        in {
            CompositeCoverageState.A_ONLY,
            CompositeCoverageState.BOTH_AGREE,
            CompositeCoverageState.BOTH_DISAGREE,
        }
        for row in gap_rows
    ):
        return HistoricalEdgeStatus.PRIMARY_COVERAGE_CHANGED

    if any(row is None or row.state is not CompositeCoverageState.B_ONLY for row in gap_rows):
        return HistoricalEdgeStatus.INCONCLUSIVE_SECONDARY_NONOBSERVATION

    anchor = by_date.get(anchor_date)
    if anchor is None or anchor.state in {
        CompositeCoverageState.A_ONLY,
        CompositeCoverageState.B_ONLY,
    }:
        return HistoricalEdgeStatus.INCONCLUSIVE_ANCHOR_MISSING
    if anchor.state is CompositeCoverageState.BOTH_DISAGREE:
        return HistoricalEdgeStatus.ANCHOR_DISAGREEMENT
    return HistoricalEdgeStatus.SECONDARY_CONFIRMS_PRIMARY_GAP
