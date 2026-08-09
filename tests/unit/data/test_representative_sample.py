from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    QualityStatus,
    SecurityType,
)
from trade_scout.data.representative_sample import (
    RepresentativeSampleError,
    RepresentativeSamplePolicy,
    assess_representative_sample,
    load_representative_sample_policy,
)


def _instrument(
    instrument_id: str,
    *,
    exchange: str = "XNYS",
    delisting_date: date | None = None,
    security_type: SecurityType = SecurityType.COMMON_STOCK,
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol=instrument_id.upper(),
        name=instrument_id,
        exchange=exchange,
        security_type=security_type,
        currency="USD",
        first_trade_date=date(2010, 1, 4),
        delisting_date=delisting_date,
        provider_ids=MappingProxyType({"primary": instrument_id}),
    )


def _bar(instrument_id: str, trade_date: date) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=10.0,
        high_raw=10.0,
        low_raw=10.0,
        close_raw=10.0,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=10.0,
        high_split_adjusted=10.0,
        low_split_adjusted=10.0,
        close_split_adjusted=10.0,
        provider_id="primary",
        dataset_version=DatasetVersion("equities-v1"),
        quality_status=QualityStatus.PASS,
    )


def _policy() -> RepresentativeSamplePolicy:
    return RepresentativeSamplePolicy(
        version="phase1-representative-v1",
        min_record_count=4,
        min_unique_instruments=2,
        min_span_days=365,
        min_delisted_instruments=1,
        min_exchanges=2,
        require_common_stock=True,
    )


def test_representative_sample_passes_only_when_all_scope_requirements_are_met() -> None:
    instruments = (
        _instrument("tsi-a", exchange="XNYS"),
        _instrument("tsi-b", exchange="XNAS", delisting_date=date(2021, 1, 4)),
    )
    bars = (
        _bar("tsi-a", date(2020, 1, 2)),
        _bar("tsi-b", date(2020, 1, 2)),
        _bar("tsi-a", date(2021, 1, 4)),
        _bar("tsi-b", date(2021, 1, 4)),
    )

    result = assess_representative_sample(bars, instruments, policy=_policy())

    assert result.accepted is True
    assert result.failures == ()
    assert result.delisted_instrument_count == 1
    assert result.exchange_count == 2


def test_small_sample_reports_each_failed_scope_condition() -> None:
    result = assess_representative_sample(
        (_bar("tsi-a", date(2020, 1, 2)),),
        (_instrument("tsi-a"),),
        policy=_policy(),
    )

    assert result.accepted is False
    assert set(result.failures) == {
        "record_count_below_minimum",
        "unique_instrument_count_below_minimum",
        "date_span_below_minimum",
        "delisted_instrument_count_below_minimum",
        "exchange_count_below_minimum",
    }


def test_unknown_bar_identity_fails_closed() -> None:
    with pytest.raises(RepresentativeSampleError, match="unknown instruments"):
        assess_representative_sample(
            (_bar("tsi-unknown", date(2020, 1, 2)),),
            (_instrument("tsi-known"),),
            policy=_policy(),
        )


def test_policy_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "version": "v1",
                "min_record_count": 1,
                "min_unique_instruments": 1,
                "min_span_days": 1,
                "min_delisted_instruments": 0,
                "min_exchanges": 1,
                "require_common_stock": True,
                "surprise": 1,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RepresentativeSampleError, match="unknown=surprise"):
        load_representative_sample_policy(path)
