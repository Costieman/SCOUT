from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.risk.initial_stops import CostModel
from trade_scout.statistics.random_timing_control import (
    run_same_instrument_random_timing_control,
)


@dataclass(frozen=True, slots=True)
class _Event:
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    ordinal: int
    event_definition_version: str = "random-control-test-v1"

    @property
    def event_id(self) -> str:
        return f"{self.instrument_id}:{self.signal_date}:{self.ordinal}"


def _bars(instrument_id: str, *, multiplier: float) -> tuple[ResearchBar, ...]:
    rows: list[ResearchBar] = []
    price = 100.0
    for index in range(60):
        drift = multiplier * (0.004 if index in {11, 12, 13, 31, 32, 33} else 0.001)
        open_price = price
        close = price * (1.0 + drift)
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId(instrument_id),
                trade_date=date(2026, 1, 1) + timedelta(days=index),
                open=open_price,
                high=max(open_price, close) * 1.002,
                low=min(open_price, close) * 0.998,
                close=close,
                volume=1_000_000.0,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("random-control-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
        price = close
    return tuple(rows)


def _events(bars: tuple[ResearchBar, ...], indices: tuple[int, ...]) -> tuple[_Event, ...]:
    return tuple(
        _Event(
            instrument_id=bars[index].instrument_id,
            signal_date=bars[index].trade_date,
            signal_index=index,
            dataset_version=str(bars[index].dataset_version),
            ordinal=ordinal,
        )
        for ordinal, index in enumerate(indices)
    )


def test_random_timing_control_is_deterministic_and_preserves_counts() -> None:
    first = _bars("rnd_a", multiplier=1.0)
    second = _bars("rnd_b", multiplier=0.7)
    source_events = (*_events(first, (10, 30)), *_events(second, (10, 30)))
    inputs = {
        "rnd_a": first,
        "rnd_b": second,
    }

    report = run_same_instrument_random_timing_control(
        inputs,
        source_events,
        horizon=5,
        cost_model=CostModel(entry_slippage_bps=5.0, exit_slippage_bps=5.0),
        signal_start=first[5].trade_date,
        signal_end=first[50].trade_date,
        iterations=250,
        random_seed=12345,
    )
    repeated = run_same_instrument_random_timing_control(
        inputs,
        source_events,
        horizon=5,
        cost_model=CostModel(entry_slippage_bps=5.0, exit_slippage_bps=5.0),
        signal_start=first[5].trade_date,
        signal_end=first[50].trade_date,
        iterations=250,
        random_seed=12345,
    )

    assert report == repeated
    assert report.sample_size == 4
    assert report.instrument_count == 2
    assert report.eligible_timing_count > report.sample_size
    assert report.comparator_kind == "same_instrument_random_eligible_timing"
    assert 0.0 < report.one_sided_empirical_p_value <= 1.0
    assert (
        report.null_interval_lower <= report.random_timing_mean_return <= report.null_interval_upper
    )


def test_random_timing_control_rejects_missing_complete_population() -> None:
    bars = _bars("rnd_short", multiplier=1.0)
    event = _events(bars, (58,))[0]

    with pytest.raises(ValueError, match="no complete hold-to-horizon events"):
        run_same_instrument_random_timing_control(
            {"rnd_short": bars},
            (event,),
            horizon=5,
            cost_model=CostModel(),
            signal_start=bars[0].trade_date,
            signal_end=bars[-1].trade_date,
            iterations=100,
            random_seed=7,
        )
