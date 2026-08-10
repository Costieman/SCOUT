from datetime import date

from trade_scout.data.composite_evidence import CompositeCoverageState, build_composite_evidence
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.reconciliation import ReconciliationTolerance


def _bar(provider: str, identity: str, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id=provider,
        provider_instrument_id=identity,
        symbol="X",
        trade_date=date(2026, 2, 2),
        open=10.0,
        high=11.0,
        low=9.0,
        close=close,
        volume=100.0,
        split_factor=None,
        dividend_cash=None,
    )


def test_disagreement_exposes_field_names() -> None:
    report = build_composite_evidence(
        instrument_id=InstrumentId("instrument:x"),
        provider_a_id="alpha_vantage",
        provider_a_instrument_id="alpha:x",
        provider_a_bars=(_bar("alpha_vantage", "alpha:x", 10.0),),
        provider_b_id="stooq",
        provider_b_instrument_id="stooq:x",
        provider_b_bars=(_bar("stooq", "stooq:x", 10.5),),
        tolerance=ReconciliationTolerance(),
    )
    row = report.rows[0]
    assert row.state is CompositeCoverageState.BOTH_DISAGREE
    assert row.differing_fields == ("close_raw",)
    assert not row.canonicalizable_without_review
