from pathlib import Path

from trade_scout.data.providers.tiingo_sp500_campaign import load_tiingo_sp500_campaign_plan


def test_checked_in_tiingo_universe_source_is_immutable() -> None:
    plan = load_tiingo_sp500_campaign_plan(Path("configs/tiingo_sp500_campaign_v0.1.json"))

    assert "/2b5795d0795302919d7a7c58ca86d74eeed8800c/" in plan.universe_source_url
    assert "/main/" not in plan.universe_source_url
