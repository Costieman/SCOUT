from __future__ import annotations

from datetime import date
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    PriceRepresentation,
    QualityStatus,
    SecurityType,
)
from trade_scout.data.serving import ResearchDataRequest, serve_research_bars
from trade_scout.universe.construction import (
    DuplicateCanonicalBarError,
    UniverseMeasurementPolicy,
    build_universe_history,
)
from trade_scout.universe.eligibility import EligibilityReason, UniverseRules


def _instrument(
    instrument_id: str,
    *,
    delisting_date: date | None = None,
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol=instrument_id.upper(),
        name=instrument_id,
        exchange="XNYS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=date(2020, 1, 2),
        delisting_date=delisting_date,
        provider_ids=MappingProxyType({"primary": instrument_id}),
    )


def _bar(
    instrument_id: str,
    trade_date: date,
    *,
    close: float,
    volume: float = 1_000_000.0,
    quality: QualityStatus = QualityStatus.PASS,
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=close,
        high_raw=close,
        low_raw=close,
        close_raw=close,
        volume_raw=volume,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close,
        low_split_adjusted=close,
        close_split_adjusted=close,
        provider_id="primary",
        dataset_version=DatasetVersion("equities-v1"),
        quality_status=quality,
    )


def _rules() -> UniverseRules:
    return UniverseRules(
        version="us-equity-v1",
        allowed_exchanges=frozenset({"XNYS"}),
        allowed_security_types=frozenset({SecurityType.COMMON_STOCK}),
        allowed_quality_states=frozenset({QualityStatus.PASS}),
        min_price=5.0,
        min_avg_dollar_volume=5_000_000.0,
        min_trading_sessions=2,
    )


def _policy() -> UniverseMeasurementPolicy:
    return UniverseMeasurementPolicy(
        version="canonical-measurements-v1",
        liquidity_lookback_sessions=2,
        reference_price_representation=PriceRepresentation.RAW,
    )


def test_history_uses_only_information_available_on_each_session() -> None:
    instrument = _instrument("tsi-1")
    bars = (
        _bar("tsi-1", date(2020, 1, 2), close=10.0, volume=1_000_000.0),
        _bar("tsi-1", date(2020, 1, 3), close=10.0, volume=1_000_000.0),
        _bar("tsi-1", date(2020, 1, 6), close=1.0, volume=1.0),
    )

    history = build_universe_history(
        bars,
        (instrument,),
        rules=_rules(),
        measurement_policy=_policy(),
    )

    first, second, third = history.snapshots
    assert first.membership[0].eligible is False
    assert first.membership[0].exclusion_reasons == (
        EligibilityReason.MISSING_LIQUIDITY,
        EligibilityReason.INSUFFICIENT_TRADING_HISTORY,
    )
    assert second.membership[0].eligible is True
    assert third.membership[0].eligible is False
    assert EligibilityReason.BELOW_MIN_PRICE in third.membership[0].exclusion_reasons
    assert EligibilityReason.BELOW_MIN_LIQUIDITY in third.membership[0].exclusion_reasons


def test_delisted_instrument_is_retained_before_delisting_and_excluded_after() -> None:
    instrument = _instrument("tsi-old", delisting_date=date(2020, 1, 3))
    bars = (
        _bar("tsi-old", date(2020, 1, 2), close=10.0),
        _bar("tsi-old", date(2020, 1, 3), close=10.0),
        _bar("tsi-other", date(2020, 1, 6), close=10.0),
    )

    history = build_universe_history(
        bars,
        (instrument, _instrument("tsi-other")),
        rules=_rules(),
        measurement_policy=_policy(),
    )
    before = next(
        record
        for record in history.snapshots[1].membership
        if record.instrument_id == InstrumentId("tsi-old")
    )
    after = next(
        record
        for record in history.snapshots[2].membership
        if record.instrument_id == InstrumentId("tsi-old")
    )

    assert before.eligible is True
    assert after.eligible is False
    assert EligibilityReason.AFTER_DELISTING in after.exclusion_reasons


def test_constructed_history_supplies_research_serving_eligibility() -> None:
    instrument = _instrument("tsi-1")
    bars = (
        _bar("tsi-1", date(2020, 1, 2), close=10.0),
        _bar("tsi-1", date(2020, 1, 3), close=10.0),
    )
    history = build_universe_history(
        bars,
        (instrument,),
        rules=_rules(),
        measurement_policy=_policy(),
    )

    served = serve_research_bars(
        bars,
        eligibility_by_key=history.eligibility_by_key,
        request=ResearchDataRequest(
            dataset_version=DatasetVersion("equities-v1"),
            start=date(2020, 1, 2),
            end=date(2020, 1, 3),
            price_representation=PriceRepresentation.RAW,
            allowed_quality_states=frozenset({QualityStatus.PASS}),
        ),
    )

    assert [row.eligibility for row in served] == [False, True]


def test_shortened_liquidity_window_is_not_treated_as_complete() -> None:
    history = build_universe_history(
        (_bar("tsi-1", date(2020, 1, 2), close=100.0, volume=100_000_000.0),),
        (_instrument("tsi-1"),),
        rules=_rules(),
        measurement_policy=_policy(),
    )

    reasons = history.snapshots[0].membership[0].exclusion_reasons
    assert EligibilityReason.MISSING_LIQUIDITY in reasons


def test_duplicate_canonical_session_fails_closed() -> None:
    bar = _bar("tsi-1", date(2020, 1, 2), close=10.0)
    with pytest.raises(DuplicateCanonicalBarError):
        build_universe_history(
            (bar, bar),
            (_instrument("tsi-1"),),
            rules=_rules(),
            measurement_policy=_policy(),
        )
