from datetime import date

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.stooq_boundary_evidence import classify_stooq_boundary_evidence


def _bar(day: date) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="stooq",
        provider_instrument_id="stooq-boundary-evidence:ABC",
        symbol="ABC",
        trade_date=day,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        price_representation=PriceRepresentation.RAW,
    )


def test_boundary_is_corroborated_only_when_both_sides_are_observed() -> None:
    boundary = date(1996, 1, 2)
    bars = tuple(
        _bar(day)
        for day in (
            date(1995, 12, 20),
            date(1995, 12, 21),
            date(1995, 12, 22),
            date(1995, 12, 26),
            date(1995, 12, 27),
            date(1996, 1, 2),
            date(1996, 1, 3),
            date(1996, 1, 4),
        )
    )

    result = classify_stooq_boundary_evidence(symbol="abc", boundary=boundary, bars=bars)

    assert result.status == "CORROBORATED"
    assert result.pre_boundary_count == 5
    assert result.on_or_after_boundary_count == 3


def test_post_boundary_only_does_not_corroborate() -> None:
    boundary = date(2000, 1, 3)
    bars = (_bar(boundary), _bar(date(2000, 1, 4)), _bar(date(2000, 1, 5)))

    result = classify_stooq_boundary_evidence(symbol="ABC", boundary=boundary, bars=bars)

    assert result.status == "POST_BOUNDARY_ONLY"
    assert result.pre_boundary_count == 0
