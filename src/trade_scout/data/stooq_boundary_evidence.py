"""Classify bounded Stooq evidence for unresolved Tiingo history boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.provider import ProviderDailyBar


@dataclass(frozen=True, slots=True)
class StooqBoundaryEvidence:
    symbol: str
    boundary: date
    pre_boundary_count: int
    on_or_after_boundary_count: int
    first_trade_date: date | None
    last_trade_date: date | None
    status: str
    reason: str


def classify_stooq_boundary_evidence(
    *,
    symbol: str,
    boundary: date,
    bars: tuple[ProviderDailyBar, ...],
    minimum_pre_boundary: int = 5,
    minimum_on_or_after: int = 3,
) -> StooqBoundaryEvidence:
    """Classify whether Stooq independently spans both sides of a Tiingo boundary.

    This is corroborating market-history evidence only. It never proves permanent issuer identity
    and therefore never directly authorizes canonical promotion.
    """

    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must be non-empty")
    if minimum_pre_boundary < 1 or minimum_on_or_after < 1:
        raise ValueError("minimum evidence counts must be positive")

    ordered = tuple(sorted(bars, key=lambda item: item.trade_date))
    pre = sum(item.trade_date < boundary for item in ordered)
    post = sum(item.trade_date >= boundary for item in ordered)
    first = ordered[0].trade_date if ordered else None
    last = ordered[-1].trade_date if ordered else None

    if pre >= minimum_pre_boundary and post >= minimum_on_or_after:
        status = "CORROBORATED"
        reason = (
            "independent Stooq observations span both sides of the Tiingo provider-history "
            "boundary; this supports boundary truncation but does not by itself prove issuer identity"
        )
    elif pre:
        status = "PRE_BOUNDARY_ONLY"
        reason = "Stooq has pre-boundary observations but insufficient on/after-boundary overlap"
    elif post:
        status = "POST_BOUNDARY_ONLY"
        reason = "Stooq observations begin on or after the Tiingo boundary"
    else:
        status = "NO_STOOQ_EVIDENCE"
        reason = "Stooq returned no bounded observations for this symbol"

    return StooqBoundaryEvidence(
        symbol=normalized,
        boundary=boundary,
        pre_boundary_count=pre,
        on_or_after_boundary_count=post,
        first_trade_date=first,
        last_trade_date=last,
        status=status,
        reason=reason,
    )


__all__ = ["StooqBoundaryEvidence", "classify_stooq_boundary_evidence"]
