from datetime import date

import pytest

from trade_scout.data.composite_evidence import (
    CompositeCoverageState,
    build_composite_evidence,
)
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.reconciliation import ReconciliationTolerance


def _bar(provider: str, provider_instrument_id: str, day: int, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id=provider,
        provider_instrument_id=provider_instrument_id,
        symbol="TEST",
        trade_date=date(2026, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100.0,
        split_factor=None,
        dividend_cash=None,
    )


def test_composite_classifies_agreement_disagreement_and_one_sided_coverage() -> None:
    report = build_composite_evidence(
        instrument_id=InstrumentId("instrument:test"),
        provider_a_id="alpha_vantage",
        provider_a_instrument_id="alpha:test",
        provider_a_bars=(
            _bar("alpha_vantage", "alpha:test", 2, 10.0),
            _bar("alpha_vantage", "alpha:test", 3, 11.0),
            _bar("alpha_vantage", "alpha:test", 4, 12.0),
        ),
        provider_b_id="stooq",
        provider_b_instrument_id="stooq:test",
        provider_b_bars=(
            _bar("stooq", "stooq:test", 2, 10.0),
            _bar("stooq", "stooq:test", 3, 11.5),
            _bar("stooq", "stooq:test", 5, 13.0),
        ),
        tolerance=ReconciliationTolerance(),
    )

    assert [row.state for row in report.rows] == [
        CompositeCoverageState.BOTH_AGREE,
        CompositeCoverageState.BOTH_DISAGREE,
        CompositeCoverageState.A_ONLY,
        CompositeCoverageState.B_ONLY,
    ]
    assert report.rows[0].canonicalizable_without_review
    assert report.rows[1].requires_discrepancy_review
    assert report.rows[2].requires_gap_review
    assert report.rows[3].requires_gap_review
    assert report.summary.row_count == 4
    assert report.summary.both_agree_count == 1
    assert report.summary.both_disagree_count == 1
    assert report.summary.a_only_count == 1
    assert report.summary.b_only_count == 1
    assert report.summary.corroborated_fraction == 0.25
    assert report.summary.one_sided_fraction == 0.5


def test_composite_rejects_wrong_identity_and_duplicate_sessions() -> None:
    with pytest.raises(ValueError, match="wrong provider identity"):
        build_composite_evidence(
            instrument_id=InstrumentId("instrument:test"),
            provider_a_id="alpha_vantage",
            provider_a_instrument_id="alpha:test",
            provider_a_bars=(_bar("alpha_vantage", "wrong", 2, 10.0),),
            provider_b_id="stooq",
            provider_b_instrument_id="stooq:test",
            provider_b_bars=(),
            tolerance=ReconciliationTolerance(),
        )

    duplicate = _bar("alpha_vantage", "alpha:test", 2, 10.0)
    with pytest.raises(ValueError, match="duplicate provider sessions"):
        build_composite_evidence(
            instrument_id=InstrumentId("instrument:test"),
            provider_a_id="alpha_vantage",
            provider_a_instrument_id="alpha:test",
            provider_a_bars=(duplicate, duplicate),
            provider_b_id="stooq",
            provider_b_instrument_id="stooq:test",
            provider_b_bars=(),
            tolerance=ReconciliationTolerance(),
        )
