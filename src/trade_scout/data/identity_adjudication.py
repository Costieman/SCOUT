"""Deterministic, fail-closed adjudication for provider-series identity evidence.

This module contains no network access and does not mutate canonical state. External-source
collectors produce :class:`IdentityEvidence`; the adjudicator combines that evidence with the
durable provider profile and returns an explicit READY or DEFER decision.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path


class IdentityAdjudicationError(RuntimeError):
    """Raised when identity-review inputs are malformed or contradictory."""


class IdentityEvidenceState(StrEnum):
    """Strength/meaning of one external identity-evidence result."""

    EXACT_PUBLIC_TRADING_START = "EXACT_PUBLIC_TRADING_START"
    CAMPAIGN_CONTINUITY = "CAMPAIGN_CONTINUITY"
    CURRENT_REGISTRANT_ONLY = "CURRENT_REGISTRANT_ONLY"
    NO_SUPPORT = "NO_SUPPORT"
    SOURCE_ERROR = "SOURCE_ERROR"


class IdentityDecisionState(StrEnum):
    """Fail-closed outcome of automated identity adjudication."""

    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True, slots=True)
class IdentityReviewInput:
    """Provider-profile facts required to adjudicate one query symbol."""

    source_symbol: str
    observed_first_date: date
    observed_last_date: date
    row_count: int
    structural_anomaly_count: int

    def __post_init__(self) -> None:
        if not self.source_symbol.strip():
            raise ValueError("source_symbol must be non-empty")
        if self.observed_last_date < self.observed_first_date:
            raise ValueError("observed_last_date cannot precede observed_first_date")
        if self.row_count < 1:
            raise ValueError("row_count must be positive")
        if self.structural_anomaly_count < 0:
            raise ValueError("structural_anomaly_count must be non-negative")


@dataclass(frozen=True, slots=True)
class IdentityEvidence:
    """Externally sourced evidence used by the deterministic adjudicator."""

    source_symbol: str
    state: IdentityEvidenceState
    source_url: str | None
    source_title: str | None
    effective_date: date | None
    regulator_id: str | None
    company_name: str | None
    exchange: str | None
    detail: str

    def __post_init__(self) -> None:
        if not self.source_symbol.strip():
            raise ValueError("source_symbol must be non-empty")
        if not self.detail.strip():
            raise ValueError("detail must be non-empty")
        if self.state in {
            IdentityEvidenceState.EXACT_PUBLIC_TRADING_START,
            IdentityEvidenceState.CAMPAIGN_CONTINUITY,
        }:
            if self.source_url is None or not self.source_url.strip():
                raise ValueError("supporting evidence requires source_url")
            if self.source_title is None or not self.source_title.strip():
                raise ValueError("supporting evidence requires source_title")
            if self.effective_date is None:
                raise ValueError("supporting evidence requires effective_date")
            if self.regulator_id is None or not self.regulator_id.strip():
                raise ValueError("supporting evidence requires regulator_id")
            if self.company_name is None or not self.company_name.strip():
                raise ValueError("supporting evidence requires company_name")
            if self.exchange is None or not self.exchange.strip():
                raise ValueError("supporting evidence requires exchange")


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    """One auditable identity-review decision; READY is not canonical promotion."""

    source_symbol: str
    state: IdentityDecisionState
    reason: str
    observed_first_date: date
    evidence: IdentityEvidence

    @property
    def ready_for_review(self) -> bool:
        return self.state is IdentityDecisionState.READY_FOR_REVIEW


@dataclass(frozen=True, slots=True)
class IdentityBatchReport:
    """Deterministic batch result suitable for private evidence persistence."""

    schema_version: str
    campaign_start: date
    decisions: tuple[IdentityDecision, ...]

    @property
    def ready_count(self) -> int:
        return sum(item.ready_for_review for item in self.decisions)

    @property
    def deferred_count(self) -> int:
        return len(self.decisions) - self.ready_count


def adjudicate_identity_case(
    review: IdentityReviewInput,
    evidence: IdentityEvidence,
    *,
    campaign_start: date,
) -> IdentityDecision:
    """Apply conservative deterministic rules without inferring unsupported lineage."""

    symbol = review.source_symbol.strip().upper()
    if evidence.source_symbol.strip().upper() != symbol:
        raise IdentityAdjudicationError(
            f"identity evidence symbol mismatch: {symbol} != {evidence.source_symbol}"
        )

    if review.structural_anomaly_count:
        return IdentityDecision(
            source_symbol=symbol,
            state=IdentityDecisionState.DEFERRED,
            reason=(
                f"durable provider profile has {review.structural_anomaly_count} structural "
                "anomaly/anomalies; identity promotion remains blocked"
            ),
            observed_first_date=review.observed_first_date,
            evidence=evidence,
        )

    if evidence.state is IdentityEvidenceState.EXACT_PUBLIC_TRADING_START:
        if evidence.effective_date == review.observed_first_date:
            return IdentityDecision(
                source_symbol=symbol,
                state=IdentityDecisionState.READY_FOR_REVIEW,
                reason=(
                    "primary-source evidence independently confirms the exact observed provider "
                    "start as the public-trading/listing boundary"
                ),
                observed_first_date=review.observed_first_date,
                evidence=evidence,
            )
        return IdentityDecision(
            source_symbol=symbol,
            state=IdentityDecisionState.DEFERRED,
            reason=(
                "primary-source public-trading boundary does not equal the durable provider start; "
                "coverage/lineage requires explicit reconciliation"
            ),
            observed_first_date=review.observed_first_date,
            evidence=evidence,
        )

    if evidence.state is IdentityEvidenceState.CAMPAIGN_CONTINUITY:
        if (
            review.observed_first_date == campaign_start
            and evidence.effective_date == campaign_start
        ):
            return IdentityDecision(
                source_symbol=symbol,
                state=IdentityDecisionState.READY_FOR_REVIEW,
                reason=(
                    "provider history begins exactly at the bounded research-campaign start and "
                    "primary-source evidence confirms same-registrant ticker/listing continuity "
                    "for that campaign boundary"
                ),
                observed_first_date=review.observed_first_date,
                evidence=evidence,
            )
        return IdentityDecision(
            source_symbol=symbol,
            state=IdentityDecisionState.DEFERRED,
            reason="campaign-continuity evidence cannot justify a non-campaign provider start",
            observed_first_date=review.observed_first_date,
            evidence=evidence,
        )

    return IdentityDecision(
        source_symbol=symbol,
        state=IdentityDecisionState.DEFERRED,
        reason=(
            "external evidence does not establish an exact public-trading boundary or bounded "
            "campaign continuity; permanent identity remains unresolved"
        ),
        observed_first_date=review.observed_first_date,
        evidence=evidence,
    )


def build_identity_batch_report(
    cases: tuple[tuple[IdentityReviewInput, IdentityEvidence], ...],
    *,
    campaign_start: date,
) -> IdentityBatchReport:
    """Adjudicate a stable ordered batch and reject duplicate symbols."""

    seen: set[str] = set()
    decisions: list[IdentityDecision] = []
    for review, evidence in sorted(cases, key=lambda item: item[0].source_symbol.upper()):
        symbol = review.source_symbol.strip().upper()
        if symbol in seen:
            raise IdentityAdjudicationError(f"duplicate identity-review symbol: {symbol}")
        seen.add(symbol)
        decisions.append(adjudicate_identity_case(review, evidence, campaign_start=campaign_start))
    return IdentityBatchReport(
        schema_version="identity-adjudication-report-v0.1",
        campaign_start=campaign_start,
        decisions=tuple(decisions),
    )


def persist_identity_batch_report(path: Path, report: IdentityBatchReport) -> None:
    """Persist an adjudication report atomically with no canonical mutation."""

    payload = {
        "schema_version": report.schema_version,
        "campaign_start": report.campaign_start.isoformat(),
        "ready_count": report.ready_count,
        "deferred_count": report.deferred_count,
        "decisions": [_decision_payload(item) for item in report.decisions],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _decision_payload(decision: IdentityDecision) -> dict[str, object]:
    evidence = asdict(decision.evidence)
    evidence["state"] = decision.evidence.state.value
    evidence["effective_date"] = (
        decision.evidence.effective_date.isoformat()
        if decision.evidence.effective_date is not None
        else None
    )
    return {
        "source_symbol": decision.source_symbol,
        "state": decision.state.value,
        "reason": decision.reason,
        "observed_first_date": decision.observed_first_date.isoformat(),
        "evidence": evidence,
    }


__all__ = [
    "IdentityAdjudicationError",
    "IdentityBatchReport",
    "IdentityDecision",
    "IdentityDecisionState",
    "IdentityEvidence",
    "IdentityEvidenceState",
    "IdentityReviewInput",
    "adjudicate_identity_case",
    "build_identity_batch_report",
    "persist_identity_batch_report",
]
