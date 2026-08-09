"""Conservative split-event evidence for characterizing Stooq price semantics.

The classifier is intentionally evidential rather than authoritative. Around a caller-supplied,
externally verified split event it compares the observed close discontinuity with two hypotheses:
unadjusted/raw-like prices and split-adjusted-like prices. Market movement can confound either
hypothesis, so ambiguous observations remain INCONCLUSIVE and no canonical price representation is
promoted automatically.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.provider import ProviderDailyBar


class StooqAdjustmentEvidenceState(StrEnum):
    """Observed behavior around a known split event."""

    RAW_LIKE = "RAW_LIKE"
    SPLIT_ADJUSTED_LIKE = "SPLIT_ADJUSTED_LIKE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class StooqSplitEvidence:
    """Auditable comparison of one Stooq series with a known split event."""

    symbol: str
    split_date: date
    split_ratio: float
    pre_trade_date: date | None
    post_trade_date: date | None
    pre_close: float | None
    post_close: float | None
    observed_pre_post_ratio: float | None
    raw_hypothesis_log_error: float | None
    adjusted_hypothesis_log_error: float | None
    state: StooqAdjustmentEvidenceState
    note: str


def characterize_stooq_split_semantics(
    bars: Sequence[ProviderDailyBar],
    *,
    symbol: str,
    split_date: date,
    split_ratio: float,
    log_error_tolerance: float = 0.18,
    separation_margin: float = 0.08,
) -> StooqSplitEvidence:
    """Classify one known split window as raw-like, adjusted-like, or inconclusive.

    ``split_ratio`` is expressed as new shares per old share, e.g. ``4.0`` for a 4-for-1 split.
    The nearest observations strictly before and on/after the supplied event date are used. The
    classifier does not infer split dates, corporate actions, or definitive adjustment semantics.
    """

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Stooq split evidence symbol must be non-empty")
    if split_ratio <= 0 or not math.isfinite(split_ratio):
        raise ValueError("split_ratio must be a finite positive value")
    if log_error_tolerance <= 0 or separation_margin < 0:
        raise ValueError("evidence tolerances must be valid positive/non-negative values")

    scoped = tuple(
        sorted(
            (
                bar
                for bar in bars
                if bar.provider_id == "stooq" and bar.symbol.upper() == normalized_symbol
            ),
            key=lambda bar: bar.trade_date,
        )
    )
    pre = tuple(bar for bar in scoped if bar.trade_date < split_date)
    post = tuple(bar for bar in scoped if bar.trade_date >= split_date)
    if not pre or not post:
        return _inconclusive(
            normalized_symbol,
            split_date,
            split_ratio,
            pre[-1] if pre else None,
            post[0] if post else None,
            "split window lacks observations on both sides of the supplied event date",
        )

    before = pre[-1]
    after = post[0]
    if before.close <= 0 or after.close <= 0:
        return _inconclusive(
            normalized_symbol,
            split_date,
            split_ratio,
            before,
            after,
            "split evidence requires positive closes on both sides of the event",
        )

    observed_ratio = before.close / after.close
    raw_error = abs(math.log(observed_ratio / split_ratio))
    adjusted_error = abs(math.log(observed_ratio))

    if raw_error <= log_error_tolerance and raw_error + separation_margin < adjusted_error:
        state = StooqAdjustmentEvidenceState.RAW_LIKE
        note = (
            "observed close discontinuity is materially closer to the supplied split ratio than "
            "to continuity; this is raw-like evidence, not definitive provider semantics"
        )
    elif adjusted_error <= log_error_tolerance and adjusted_error + separation_margin < raw_error:
        state = StooqAdjustmentEvidenceState.SPLIT_ADJUSTED_LIKE
        note = (
            "observed closes remain materially closer to continuity than to the supplied split "
            "ratio; this is split-adjusted-like evidence, not definitive provider semantics"
        )
    else:
        state = StooqAdjustmentEvidenceState.INCONCLUSIVE
        note = (
            "observed split-window behavior does not separate raw and split-adjusted hypotheses "
            "within the configured conservative tolerances"
        )

    return StooqSplitEvidence(
        symbol=normalized_symbol,
        split_date=split_date,
        split_ratio=split_ratio,
        pre_trade_date=before.trade_date,
        post_trade_date=after.trade_date,
        pre_close=before.close,
        post_close=after.close,
        observed_pre_post_ratio=observed_ratio,
        raw_hypothesis_log_error=raw_error,
        adjusted_hypothesis_log_error=adjusted_error,
        state=state,
        note=note,
    )


def _inconclusive(
    symbol: str,
    split_date: date,
    split_ratio: float,
    before: ProviderDailyBar | None,
    after: ProviderDailyBar | None,
    note: str,
) -> StooqSplitEvidence:
    return StooqSplitEvidence(
        symbol=symbol,
        split_date=split_date,
        split_ratio=split_ratio,
        pre_trade_date=before.trade_date if before is not None else None,
        post_trade_date=after.trade_date if after is not None else None,
        pre_close=before.close if before is not None else None,
        post_close=after.close if after is not None else None,
        observed_pre_post_ratio=None,
        raw_hypothesis_log_error=None,
        adjusted_hypothesis_log_error=None,
        state=StooqAdjustmentEvidenceState.INCONCLUSIVE,
        note=note,
    )
