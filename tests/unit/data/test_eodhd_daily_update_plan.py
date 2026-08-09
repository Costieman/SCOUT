from datetime import date

import pytest

from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign_plan import EodhdCampaignPlan
from trade_scout.data.providers.eodhd_campaign_suite import EodhdCampaignSuiteCase
from trade_scout.data.providers.eodhd_daily_update_plan import plan_eodhd_daily_update_probe


def _case(
    case_id: str,
    symbol: str,
    start: date,
    end: date,
    *,
    active: bool,
) -> EodhdCampaignSuiteCase:
    return EodhdCampaignSuiteCase(
        case_id=case_id,
        symbol=symbol,
        start=start,
        end=end,
        expected_active=active,
        dataset_version=DatasetVersion(f"case-{case_id}"),
    )


def test_probe_uses_latest_active_case_and_tail_window() -> None:
    campaign = EodhdCampaignPlan(
        plan_version="test",
        cases=(
            _case("a", "AAA.US", date(2020, 1, 1), date(2025, 12, 31), active=True),
            _case("b", "BBB.US", date(2020, 1, 1), date(2026, 8, 8), active=True),
            _case("z", "OLD.US", date(2010, 1, 1), date(2026, 8, 9), active=False),
        ),
    )

    probe = plan_eodhd_daily_update_probe(campaign, run_date=date(2026, 8, 9))

    assert probe.symbol == "BBB.US"
    assert probe.start == date(2026, 7, 25)
    assert probe.end == date(2026, 8, 8)
    assert probe.target_dataset_version == DatasetVersion("eodhd-phase1-daily-update-20260809")


def test_probe_clamps_lookback_to_case_start() -> None:
    campaign = EodhdCampaignPlan(
        plan_version="test",
        cases=(
            _case("a", "AAA.US", date(2026, 8, 1), date(2026, 8, 8), active=True),
            _case("z", "OLD.US", date(2010, 1, 1), date(2015, 1, 1), active=False),
        ),
    )

    probe = plan_eodhd_daily_update_probe(
        campaign,
        run_date=date(2026, 8, 9),
        lookback_days=30,
    )

    assert probe.start == date(2026, 8, 1)


def test_probe_rejects_nonpositive_lookback() -> None:
    campaign = EodhdCampaignPlan(
        plan_version="test",
        cases=(
            _case("a", "AAA.US", date(2020, 1, 1), date(2026, 8, 8), active=True),
            _case("z", "OLD.US", date(2010, 1, 1), date(2015, 1, 1), active=False),
        ),
    )

    with pytest.raises(ValueError, match="lookback_days"):
        plan_eodhd_daily_update_probe(campaign, run_date=date(2026, 8, 9), lookback_days=0)
