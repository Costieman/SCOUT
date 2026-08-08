from datetime import date
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    QualityStatus,
    SecurityType,
)
from trade_scout.universe.eligibility import (
    EligibilityObservation,
    EligibilityReason,
    FutureEligibilityDataError,
    MixedDatasetVersionError,
    UniverseRules,
    build_universe_snapshot,
    evaluate_eligibility,
)


def _instrument(
    *,
    instrument_id: str = "tsi-1",
    exchange: str = "XNYS",
    security_type: SecurityType = SecurityType.COMMON_STOCK,
    first_trade_date: date | None = date(2010, 1, 4),
    delisting_date: date | None = None,
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol="AAA",
        name="Example Corp",
        exchange=exchange,
        security_type=security_type,
        currency="USD",
        first_trade_date=first_trade_date,
        delisting_date=delisting_date,
        provider_ids=MappingProxyType({"primary": instrument_id}),
    )


def _rules() -> UniverseRules:
    return UniverseRules(
        version="us-equity-v0.1.0",
        allowed_exchanges=frozenset({"XNYS", "XNAS", "XASE"}),
        allowed_security_types=frozenset({SecurityType.COMMON_STOCK}),
        allowed_quality_states=frozenset({QualityStatus.PASS}),
        min_price=5.0,
        min_avg_dollar_volume=5_000_000.0,
        min_trading_sessions=200,
    )


def _observation(
    *,
    instrument: InstrumentRecord | None = None,
    measurement_as_of: date = date(2020, 6, 30),
    price: float | None = 25.0,
    liquidity: float | None = 20_000_000.0,
    sessions: int | None = 2_000,
    quality: QualityStatus = QualityStatus.PASS,
    dataset_version: str = "equities-v1.0.0",
) -> EligibilityObservation:
    return EligibilityObservation(
        instrument=instrument or _instrument(),
        measurement_as_of=measurement_as_of,
        reference_price=price,
        avg_dollar_volume=liquidity,
        trading_sessions=sessions,
        quality_status=quality,
        dataset_version=DatasetVersion(dataset_version),
    )


def test_eligible_historical_common_stock_passes() -> None:
    result = evaluate_eligibility(
        _observation(),
        as_of=date(2020, 6, 30),
        rules=_rules(),
    )

    assert result.eligible is True
    assert result.exclusion_reasons == ()


def test_instrument_is_not_projected_before_ipo() -> None:
    result = evaluate_eligibility(
        _observation(instrument=_instrument(first_trade_date=date(2021, 1, 4))),
        as_of=date(2020, 6, 30),
        rules=_rules(),
    )

    assert result.eligible is False
    assert EligibilityReason.BEFORE_FIRST_TRADE in result.exclusion_reasons


def test_delisted_security_remains_eligible_before_delisting() -> None:
    instrument = _instrument(delisting_date=date(2020, 12, 31))

    before = evaluate_eligibility(
        _observation(instrument=instrument),
        as_of=date(2020, 6, 30),
        rules=_rules(),
    )
    after = evaluate_eligibility(
        _observation(instrument=instrument, measurement_as_of=date(2021, 1, 4)),
        as_of=date(2021, 1, 4),
        rules=_rules(),
    )

    assert before.eligible is True
    assert after.eligible is False
    assert EligibilityReason.AFTER_DELISTING in after.exclusion_reasons


def test_future_liquidity_snapshot_is_rejected_instead_of_used() -> None:
    with pytest.raises(FutureEligibilityDataError):
        evaluate_eligibility(
            _observation(measurement_as_of=date(2020, 7, 1)),
            as_of=date(2020, 6, 30),
            rules=_rules(),
        )


def test_missing_required_measurements_remain_ineligible() -> None:
    result = evaluate_eligibility(
        _observation(price=None, liquidity=None, sessions=None),
        as_of=date(2020, 6, 30),
        rules=_rules(),
    )

    assert result.eligible is False
    assert result.exclusion_reasons == (
        EligibilityReason.MISSING_REFERENCE_PRICE,
        EligibilityReason.MISSING_LIQUIDITY,
        EligibilityReason.MISSING_TRADING_HISTORY,
    )


def test_non_common_security_and_bad_quality_are_explicitly_excluded() -> None:
    result = evaluate_eligibility(
        _observation(
            instrument=_instrument(security_type=SecurityType.ETF),
            quality=QualityStatus.QUARANTINE,
        ),
        as_of=date(2020, 6, 30),
        rules=_rules(),
    )

    assert EligibilityReason.SECURITY_TYPE_EXCLUDED in result.exclusion_reasons
    assert EligibilityReason.QUALITY_NOT_ALLOWED in result.exclusion_reasons


def test_snapshot_rejects_mixed_dataset_versions() -> None:
    with pytest.raises(MixedDatasetVersionError):
        build_universe_snapshot(
            [
                _observation(dataset_version="equities-v1.0.0"),
                _observation(
                    instrument=_instrument(instrument_id="tsi-2"),
                    dataset_version="equities-v1.0.1",
                ),
            ],
            as_of=date(2020, 6, 30),
            rules=_rules(),
        )


def test_snapshot_order_is_deterministic() -> None:
    snapshot = build_universe_snapshot(
        [
            _observation(instrument=_instrument(instrument_id="tsi-2")),
            _observation(instrument=_instrument(instrument_id="tsi-1")),
        ],
        as_of=date(2020, 6, 30),
        rules=_rules(),
    )

    assert snapshot.eligible_instrument_ids == (InstrumentId("tsi-1"), InstrumentId("tsi-2"))
