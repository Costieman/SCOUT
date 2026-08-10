from datetime import date

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    QualityStatus,
    SecurityType,
    SymbolHistoryRecord,
)
from trade_scout.data.instrument_master import (
    SymbolHistoryConflictError,
    instrument_from_primary_provider,
)
from trade_scout.data.normalization import (
    NormalizationRule,
    normalize_provider_daily_bars,
    normalize_provider_daily_bars_identity_aware,
)
from trade_scout.data.provider import ProviderDailyBar, ProviderInstrument

VERSION = DatasetVersion("equities_daily_v0.1.0")


def _instrument(
    *, provider_instrument_id: str = "asset-1", symbol: str = "AAA"
) -> ProviderInstrument:
    return ProviderInstrument(
        provider_id="primary",
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        name="Example Corp",
        exchange="XNYS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        active=True,
        first_trade_date=date(2010, 1, 4),
        end_date=None,
        source_fields={},
    )


def _bar(
    *,
    provider_instrument_id: str = "asset-1",
    symbol: str = "AAA",
    trade_date: date = date(2026, 8, 7),
    high: float = 105.0,
    low: float = 99.0,
    close: float = 103.0,
    split_factor: float | None = 1.0,
    dividend_cash: float | None = 0.0,
    adjusted_open: float | None = None,
    adjusted_high: float | None = None,
    adjusted_low: float | None = None,
    adjusted_close: float | None = None,
) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="primary",
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        trade_date=trade_date,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
        split_factor=split_factor,
        dividend_cash=dividend_cash,
        adjusted_open=adjusted_open,
        adjusted_high=adjusted_high,
        adjusted_low=adjusted_low,
        adjusted_close=adjusted_close,
    )


def _history(
    canonical_symbol: str,
    canonical_instrument: object,
    *,
    effective_from: date,
    effective_to: date | None,
) -> SymbolHistoryRecord:
    instrument_id = getattr(canonical_instrument, "instrument_id")
    return SymbolHistoryRecord(
        instrument_id=instrument_id,
        symbol=canonical_symbol,
        exchange="XNAS",
        effective_from=effective_from,
        effective_to=effective_to,
    )


def test_normalization_uses_exact_provider_identity_not_ticker() -> None:
    canonical = instrument_from_primary_provider(_instrument(symbol="AAA"))

    result = normalize_provider_daily_bars(
        [_bar(provider_instrument_id="different-asset", symbol="AAA")],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.bars == ()
    assert result.status is QualityStatus.QUARANTINE
    assert result.normalization_issues[0].rule is NormalizationRule.UNRESOLVED_INSTRUMENT


def test_raw_only_bar_normalizes_when_adjustment_metadata_is_explicit() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [_bar()],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.status is QualityStatus.PASS
    assert len(result.bars) == 1
    normalized = result.bars[0]
    assert normalized.instrument_id == canonical.instrument_id
    assert normalized.dataset_version == VERSION
    assert normalized.close_split_adjusted is None
    assert normalized.quality_status is QualityStatus.PASS


def test_complete_adjusted_ohlc_is_preserved() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [
            _bar(
                adjusted_open=50.0,
                adjusted_high=52.5,
                adjusted_low=49.5,
                adjusted_close=51.5,
            )
        ],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.bars[0].close_split_adjusted == 51.5


def test_missing_split_factor_is_quarantined_not_assumed_to_be_one() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [_bar(split_factor=None)],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.bars == ()
    assert result.normalization_issues[0].rule is NormalizationRule.MISSING_SPLIT_FACTOR


def test_missing_dividend_cash_is_quarantined_not_assumed_to_be_zero() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [_bar(dividend_cash=None)],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.bars == ()
    assert result.normalization_issues[0].rule is NormalizationRule.MISSING_DIVIDEND_CASH


def test_partial_adjusted_prices_do_not_silently_fall_back() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [_bar(adjusted_open=50.0, adjusted_close=51.5)],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.bars == ()
    assert result.normalization_issues[0].rule is NormalizationRule.PARTIAL_ADJUSTED_OHLC


def test_structural_quality_failures_are_attached_to_canonical_bar() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [_bar(high=95.0, low=99.0)],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.status is QualityStatus.REJECT
    assert result.bars[0].quality_status is QualityStatus.REJECT
    assert result.quality_issues


def test_duplicate_instrument_session_marks_both_canonical_records_reject() -> None:
    canonical = instrument_from_primary_provider(_instrument())

    result = normalize_provider_daily_bars(
        [_bar(), _bar()],
        instruments=[canonical],
        dataset_version=VERSION,
    )

    assert result.status is QualityStatus.REJECT
    assert all(bar.quality_status is QualityStatus.REJECT for bar in result.bars)


def test_identity_aware_normalization_allows_current_query_symbol_over_historical_symbol() -> None:
    canonical = instrument_from_primary_provider(
        _instrument(provider_instrument_id="asset-axon", symbol="AXON")
    )
    history = [
        _history(
            "TASR",
            canonical,
            effective_from=date(2001, 1, 1),
            effective_to=date(2017, 4, 5),
        ),
        _history(
            "AAXN",
            canonical,
            effective_from=date(2017, 4, 6),
            effective_to=date(2021, 1, 25),
        ),
        _history("AXON", canonical, effective_from=date(2021, 1, 26), effective_to=None),
    ]

    result = normalize_provider_daily_bars_identity_aware(
        [
            _bar(
                provider_instrument_id="asset-axon",
                symbol="AXON",
                trade_date=date(2001, 6, 7),
            )
        ],
        instruments=[canonical],
        symbol_history=history,
        dataset_version=VERSION,
    )

    assert result.status is QualityStatus.PASS
    assert result.normalization_issues == ()
    assert result.bars[0].instrument_id == canonical.instrument_id
    assert result.bars[0].trade_date == date(2001, 6, 7)


def test_identity_aware_normalization_quarantines_missing_historical_symbol_coverage() -> None:
    canonical = instrument_from_primary_provider(
        _instrument(provider_instrument_id="asset-axon", symbol="AXON")
    )
    history = [
        _history("AXON", canonical, effective_from=date(2021, 1, 26), effective_to=None)
    ]

    result = normalize_provider_daily_bars_identity_aware(
        [
            _bar(
                provider_instrument_id="asset-axon",
                symbol="AXON",
                trade_date=date(2001, 6, 7),
            )
        ],
        instruments=[canonical],
        symbol_history=history,
        dataset_version=VERSION,
    )

    assert result.bars == ()
    assert result.status is QualityStatus.QUARANTINE
    assert len(result.normalization_issues) == 1
    assert (
        result.normalization_issues[0].rule
        is NormalizationRule.UNRESOLVED_SYMBOL_HISTORY
    )


def test_identity_aware_normalization_propagates_overlapping_symbol_history_conflict() -> None:
    canonical = instrument_from_primary_provider(_instrument())
    history = [
        _history(
            "OLD",
            canonical,
            effective_from=date(2020, 1, 1),
            effective_to=date(2026, 8, 7),
        ),
        _history("AAA", canonical, effective_from=date(2026, 1, 1), effective_to=None),
    ]

    with pytest.raises(SymbolHistoryConflictError, match="multiple symbol assignments"):
        normalize_provider_daily_bars_identity_aware(
            [_bar()],
            instruments=[canonical],
            symbol_history=history,
            dataset_version=VERSION,
        )
