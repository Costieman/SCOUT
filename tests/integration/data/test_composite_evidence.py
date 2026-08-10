from datetime import date

from trade_scout.data.composite_evidence import CompositeCoverageState, build_composite_evidence
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.reconciliation import ReconciliationTolerance


def test_tolerance_can_corroborate_small_provider_price_difference() -> None:
    alpha = ProviderDailyBar(
        provider_id="alpha_vantage",
        provider_instrument_id="alpha_vantage:symbol:SPY",
        symbol="SPY",
        trade_date=date(2026, 1, 2),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1000.0,
        split_factor=None,
        dividend_cash=None,
    )
    stooq = ProviderDailyBar(
        provider_id="stooq",
        provider_instrument_id="stooq:spy",
        symbol="SPY.US",
        trade_date=date(2026, 1, 2),
        open=100.00001,
        high=101.00001,
        low=99.00001,
        close=100.00001,
        volume=1000.0,
        split_factor=None,
        dividend_cash=None,
    )
    report = build_composite_evidence(
        instrument_id=InstrumentId("instrument:spy"),
        provider_a_id="alpha_vantage",
        provider_a_instrument_id="alpha_vantage:symbol:SPY",
        provider_a_bars=(alpha,),
        provider_b_id="stooq",
        provider_b_instrument_id="stooq:spy",
        provider_b_bars=(stooq,),
        tolerance=ReconciliationTolerance(price_relative=0.000001),
    )
    assert report.rows[0].state is CompositeCoverageState.BOTH_AGREE
