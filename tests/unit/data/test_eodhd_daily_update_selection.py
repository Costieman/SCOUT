from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)
from trade_scout.data.providers.eodhd_daily_update import matching_eodhd_parent_bars


def _bar(instrument: str, trade_date: date, *, version: str) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument),
        trade_date=trade_date,
        open_raw=10.0,
        high_raw=11.0,
        low_raw=9.0,
        close_raw=10.5,
        volume_raw=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=10.0,
        high_split_adjusted=11.0,
        low_split_adjusted=9.0,
        close_split_adjusted=10.5,
        provider_id="eodhd",
        dataset_version=DatasetVersion(version),
        quality_status=QualityStatus.PASS,
    )


def test_matching_parent_bars_selects_only_incoming_instrument() -> None:
    parent = (
        _bar("instrument-a", date(2026, 8, 6), version="parent-v1"),
        _bar("instrument-a", date(2026, 8, 7), version="parent-v1"),
        _bar("instrument-b", date(2026, 8, 7), version="parent-v1"),
    )
    incoming = (_bar("instrument-a", date(2026, 8, 7), version="target-v2"),)

    matched = matching_eodhd_parent_bars(parent, incoming)

    assert len(matched) == 2
    assert {str(bar.instrument_id) for bar in matched} == {"instrument-a"}


def test_matching_parent_bars_rejects_missing_parent_identity() -> None:
    parent = (_bar("instrument-a", date(2026, 8, 7), version="parent-v1"),)
    incoming = (_bar("instrument-b", date(2026, 8, 7), version="target-v2"),)

    with pytest.raises(ValueError, match="absent from the parent"):
        matching_eodhd_parent_bars(parent, incoming)


def test_matching_parent_bars_rejects_multi_instrument_incoming() -> None:
    parent = (
        _bar("instrument-a", date(2026, 8, 7), version="parent-v1"),
        _bar("instrument-b", date(2026, 8, 7), version="parent-v1"),
    )
    incoming = (
        _bar("instrument-a", date(2026, 8, 7), version="target-v2"),
        _bar("instrument-b", date(2026, 8, 7), version="target-v2"),
    )

    with pytest.raises(ValueError, match="exactly one incoming instrument"):
        matching_eodhd_parent_bars(parent, incoming)
