from datetime import date

import pytest

from trade_scout.data.providers.tiingo_split_preview import (
    TiingoSplitPreviewError,
    build_tiingo_split_only_provider_bars,
)


def _row(
    day: str,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1000.0,
    split_factor: float = 1.0,
    dividend: float = 0.0,
    adj_open: float | None = None,
    adj_high: float | None = None,
    adj_low: float | None = None,
    adj_close: float | None = None,
) -> dict[str, object]:
    return {
        "date": f"{day}T00:00:00+00:00",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "splitFactor": split_factor,
        "divCash": dividend,
        "adjOpen": open_ if adj_open is None else adj_open,
        "adjHigh": high if adj_high is None else adj_high,
        "adjLow": low if adj_low is None else adj_low,
        "adjClose": close if adj_close is None else adj_close,
    }


def test_forward_split_applies_event_ratio_only_to_earlier_rows() -> None:
    rows = [
        _row(
            "2020-08-28",
            open_=400.0,
            high=404.0,
            low=396.0,
            close=400.0,
            adj_open=100.0,
            adj_high=101.0,
            adj_low=99.0,
            adj_close=100.0,
        ),
        _row(
            "2020-08-31",
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            split_factor=4.0,
        ),
        _row("2020-09-01", open_=102.0, high=103.0, low=101.0, close=102.0),
    ]

    result = build_tiingo_split_only_provider_bars(
        rows,
        query_symbol="AAPL",
        provider_instrument_id="tiingo-series:test-aapl",
    )

    assert [bar.trade_date for bar in result.bars] == [
        date(2020, 8, 28),
        date(2020, 8, 31),
        date(2020, 9, 1),
    ]
    assert result.bars[0].split_factor == pytest.approx(0.25)
    assert result.bars[0].adjusted_close == pytest.approx(100.0)
    assert result.bars[1].split_factor == pytest.approx(1.0)
    assert result.bars[1].adjusted_close == pytest.approx(100.0)
    assert result.bars[2].split_factor == pytest.approx(1.0)
    assert result.split_events[0].effective_date == date(2020, 8, 31)
    assert result.split_events[0].split_ratio == pytest.approx(4.0)
    assert result.tiingo_adjusted_cross_check_eligible is True
    assert result.tiingo_adjusted_cross_check_mismatch_count == 0


def test_reverse_split_raises_prior_price_basis_via_reciprocal_product() -> None:
    rows = [
        _row(
            "2024-01-02",
            open_=10.0,
            high=11.0,
            low=9.0,
            close=10.0,
            adj_open=100.0,
            adj_high=110.0,
            adj_low=90.0,
            adj_close=100.0,
        ),
        _row(
            "2024-01-03",
            open_=100.0,
            high=110.0,
            low=90.0,
            close=100.0,
            split_factor=0.1,
        ),
    ]

    result = build_tiingo_split_only_provider_bars(
        rows,
        query_symbol="TEST",
        provider_instrument_id="tiingo-series:test",
    )

    assert result.bars[0].split_factor == pytest.approx(10.0)
    assert result.bars[0].adjusted_close == pytest.approx(100.0)
    assert result.bars[1].split_factor == pytest.approx(1.0)
    assert result.tiingo_adjusted_cross_check_mismatch_count == 0


def test_dividends_do_not_enter_split_only_multiplier_or_vendor_cross_check() -> None:
    rows = [
        _row(
            "2024-02-01",
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            dividend=1.0,
            adj_open=98.0,
            adj_high=99.0,
            adj_low=97.0,
            adj_close=98.0,
        ),
        _row("2024-02-02", open_=101.0, high=102.0, low=100.0, close=101.0),
    ]

    result = build_tiingo_split_only_provider_bars(
        rows,
        query_symbol="DIV",
        provider_instrument_id="tiingo-series:div",
    )

    assert result.dividend_event_count == 1
    assert result.bars[0].split_factor == pytest.approx(1.0)
    assert result.bars[0].adjusted_close == pytest.approx(100.0)
    assert result.bars[0].dividend_cash == pytest.approx(1.0)
    assert result.tiingo_adjusted_cross_check_eligible is False
    assert result.tiingo_adjusted_cross_check_field_count == 0
    assert result.tiingo_adjusted_cross_check_mismatch_count == 0
    assert result.tiingo_adjusted_cross_check_max_relative_error is None


def test_nonpositive_split_factor_is_rejected() -> None:
    rows = [
        _row(
            "2024-03-01",
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            split_factor=0.0,
        )
    ]

    with pytest.raises(TiingoSplitPreviewError, match="splitFactor must be positive"):
        build_tiingo_split_only_provider_bars(
            rows,
            query_symbol="BAD",
            provider_instrument_id="tiingo-series:bad",
        )


def test_duplicate_or_unsorted_dates_are_rejected() -> None:
    rows = [
        _row("2024-03-02", open_=100.0, high=101.0, low=99.0, close=100.0),
        _row("2024-03-01", open_=100.0, high=101.0, low=99.0, close=100.0),
    ]

    with pytest.raises(TiingoSplitPreviewError, match="strictly date-increasing"):
        build_tiingo_split_only_provider_bars(
            rows,
            query_symbol="BAD",
            provider_instrument_id="tiingo-series:bad",
        )
