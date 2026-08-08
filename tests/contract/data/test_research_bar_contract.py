from datetime import date

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    PriceRepresentationUnavailableError,
    QualityStatus,
    to_research_bar,
)


def _bar(*, adjusted: bool = True) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId("inst-1"),
        trade_date=date(2026, 8, 7),
        open_raw=100.0,
        high_raw=105.0,
        low_raw=99.0,
        close_raw=103.0,
        volume_raw=1_000_000,
        split_factor=0.5,
        dividend_cash=0.0,
        open_split_adjusted=50.0 if adjusted else None,
        high_split_adjusted=52.5 if adjusted else None,
        low_split_adjusted=49.5 if adjusted else None,
        close_split_adjusted=51.5 if adjusted else None,
        provider_id="test-provider",
        dataset_version=DatasetVersion("equities_daily_v0.1.0"),
        quality_status=QualityStatus.PASS,
    )


def test_raw_research_bar_is_explicit() -> None:
    result = to_research_bar(_bar(), representation=PriceRepresentation.RAW, eligibility=True)

    assert result.close == 103.0
    assert result.price_representation is PriceRepresentation.RAW
    assert result.eligibility is True


def test_split_adjusted_research_bar_is_explicit() -> None:
    result = to_research_bar(
        _bar(), representation=PriceRepresentation.SPLIT_ADJUSTED, eligibility=False
    )

    assert result.close == 51.5
    assert result.price_representation is PriceRepresentation.SPLIT_ADJUSTED
    assert result.eligibility is False


def test_missing_adjusted_prices_fail_instead_of_falling_back() -> None:
    with pytest.raises(PriceRepresentationUnavailableError):
        to_research_bar(
            _bar(adjusted=False),
            representation=PriceRepresentation.SPLIT_ADJUSTED,
            eligibility=True,
        )
