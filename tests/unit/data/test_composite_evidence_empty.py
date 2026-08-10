from trade_scout.data.composite_evidence import build_composite_evidence
from trade_scout.data.contracts import InstrumentId
from trade_scout.data.reconciliation import ReconciliationTolerance


def test_empty_composite_report_has_no_fraction_claims() -> None:
    report = build_composite_evidence(
        instrument_id=InstrumentId("instrument:none"),
        provider_a_id="alpha_vantage",
        provider_a_instrument_id="alpha:none",
        provider_a_bars=(),
        provider_b_id="stooq",
        provider_b_instrument_id="stooq:none",
        provider_b_bars=(),
        tolerance=ReconciliationTolerance(),
    )
    assert report.rows == ()
    assert report.summary.row_count == 0
    assert report.summary.corroborated_fraction is None
    assert report.summary.one_sided_fraction is None
