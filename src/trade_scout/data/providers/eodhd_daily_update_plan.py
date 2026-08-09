"""Deterministic planning for one live EODHD correction-lookback probe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign_plan import EodhdCampaignPlan


@dataclass(frozen=True, slots=True)
class EodhdDailyUpdateProbePlan:
    """One bounded live probe derived only from the frozen representative campaign plan."""

    symbol: str
    start: date
    end: date
    target_dataset_version: DatasetVersion


def plan_eodhd_daily_update_probe(
    campaign: EodhdCampaignPlan,
    *,
    run_date: date,
    lookback_days: int = 14,
) -> EodhdDailyUpdateProbePlan:
    """Choose one active case and a deterministic tail window for live overlap evidence."""

    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")
    active = tuple(case for case in campaign.cases if case.expected_active)
    if not active:
        raise ValueError("daily-update probe requires at least one active campaign case")

    case = sorted(active, key=lambda item: (-item.end.toordinal(), item.case_id))[0]
    start = max(case.start, case.end - timedelta(days=lookback_days))
    return EodhdDailyUpdateProbePlan(
        symbol=case.symbol,
        start=start,
        end=case.end,
        target_dataset_version=DatasetVersion(
            f"eodhd-phase1-daily-update-{run_date.strftime('%Y%m%d')}"
        ),
    )
