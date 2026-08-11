"""Quantify how much two providers complement each other over expected sessions.

This module is intentionally downstream of raw cross-provider evidence. It does not retrieve data,
choose a canonical source, fill gaps, or resolve disagreements. It only measures how much expected
session coverage would improve if independently reviewed observations from either provider were
available for adjudication.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from trade_scout.data.composite_evidence import CompositeEvidenceReport


@dataclass(frozen=True, slots=True)
class ProviderComplementaritySummary:
    """Expected-session coverage summary for one reviewed instrument window."""

    expected_session_count: int
    provider_a_session_count: int
    provider_b_session_count: int
    union_session_count: int
    both_agree_count: int
    both_disagree_count: int
    provider_a_only_count: int
    provider_b_only_count: int
    both_missing_count: int

    @property
    def complementary_session_count(self) -> int:
        """Sessions observed by exactly one provider and therefore requiring review."""

        return self.provider_a_only_count + self.provider_b_only_count

    @property
    def provider_a_coverage_fraction(self) -> float | None:
        return _fraction(self.provider_a_session_count, self.expected_session_count)

    @property
    def provider_b_coverage_fraction(self) -> float | None:
        return _fraction(self.provider_b_session_count, self.expected_session_count)

    @property
    def union_coverage_fraction(self) -> float | None:
        return _fraction(self.union_session_count, self.expected_session_count)

    @property
    def union_gain_over_a_fraction(self) -> float | None:
        """Expected-session coverage added by B-only observations relative to A alone."""

        return _fraction(self.provider_b_only_count, self.expected_session_count)

    @property
    def union_gain_over_b_fraction(self) -> float | None:
        """Expected-session coverage added by A-only observations relative to B alone."""

        return _fraction(self.provider_a_only_count, self.expected_session_count)


def summarize_provider_complementarity(
    evidence: CompositeEvidenceReport,
    *,
    expected_sessions: Iterable[date],
) -> ProviderComplementaritySummary:
    """Summarize provider complementarity without promoting or fabricating observations."""

    expected_sequence = tuple(expected_sessions)
    expected = frozenset(expected_sequence)
    if len(expected) != len(expected_sequence):
        raise ValueError("expected session input contains duplicate dates")

    evidence_dates = tuple(row.trade_date for row in evidence.rows)
    if len(set(evidence_dates)) != len(evidence_dates):
        raise ValueError("composite evidence contains duplicate session dates")
    unexpected = set(evidence_dates) - expected
    if unexpected:
        rendered = ", ".join(day.isoformat() for day in sorted(unexpected))
        raise ValueError(f"composite evidence contains unexpected sessions: {rendered}")

    summary = evidence.summary
    both_count = summary.both_agree_count + summary.both_disagree_count
    provider_a_count = both_count + summary.a_only_count
    provider_b_count = both_count + summary.b_only_count
    union_count = len(evidence_dates)

    return ProviderComplementaritySummary(
        expected_session_count=len(expected),
        provider_a_session_count=provider_a_count,
        provider_b_session_count=provider_b_count,
        union_session_count=union_count,
        both_agree_count=summary.both_agree_count,
        both_disagree_count=summary.both_disagree_count,
        provider_a_only_count=summary.a_only_count,
        provider_b_only_count=summary.b_only_count,
        both_missing_count=len(expected - set(evidence_dates)),
    )


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
