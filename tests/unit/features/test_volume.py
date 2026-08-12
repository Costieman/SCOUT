from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.features.volume import relative_volume


def _bar(index: int, volume: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_volume"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=volume,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_relative_volume_excludes_signal_bar_from_baseline() -> None:
    bars = tuple([_bar(index, 1_000_000.0) for index in range(20)] + [_bar(20, 2_000_000.0)])

    assert relative_volume(bars, signal_index=20, lookback_sessions=20) == 2.0


def test_relative_volume_requires_complete_prior_window() -> None:
    bars = tuple(_bar(index, 1_000_000.0) for index in range(20))

    assert relative_volume(bars, signal_index=19, lookback_sessions=20) is None


def test_relative_volume_does_not_change_when_future_volume_changes() -> None:
    bars = tuple(
        [_bar(index, 1_000_000.0) for index in range(20)]
        + [_bar(20, 1_500_000.0), _bar(21, 1_000_000.0)]
    )
    changed = list(bars)
    changed[21] = replace(changed[21], volume=100_000_000.0)

    assert relative_volume(bars, signal_index=20, lookback_sessions=20) == relative_volume(
        tuple(changed), signal_index=20, lookback_sessions=20
    )
