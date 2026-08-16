from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.outcomes import ExtremeOrder, OutcomePathStatus, measure_outcome_paths


@dataclass(frozen=True, slots=True)
class IndependentEvent:
    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str = "independent-outcome-test-v1"


def _bar(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_outcome_path"),
        trade_date=date(2024, 1, 2) + timedelta(days=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("outcome-path-test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _event(bars: tuple[ResearchBar, ...], signal_index: int) -> IndependentEvent:
    return IndependentEvent(
        event_id=f"event-{signal_index}",
        instrument_id=bars[signal_index].instrument_id,
        signal_date=bars[signal_index].trade_date,
        signal_index=signal_index,
        dataset_version=str(bars[signal_index].dataset_version),
    )


def test_complete_path_measures_timing_gaps_and_drawdown_bounds() -> None:
    bars = (
        _bar(0, open_=99.0, high=101.0, low=98.0, close=100.0),
        _bar(1, open_=95.0, high=103.0, low=94.0, close=101.0),
        _bar(2, open_=102.0, high=105.0, low=100.0, close=104.0),
        _bar(3, open_=103.0, high=106.0, low=99.0, close=105.0),
    )

    outcome = measure_outcome_paths(bars, (_event(bars, 0),), horizons=(3,))[0]

    assert outcome.status is OutcomePathStatus.COMPLETE
    assert outcome.observed_sessions == 3
    assert outcome.entry_price == 95.0
    assert outcome.forward_return == pytest.approx(105.0 / 95.0 - 1.0)
    assert outcome.mfe == pytest.approx(106.0 / 95.0 - 1.0)
    assert outcome.mae == pytest.approx(94.0 / 95.0 - 1.0)
    assert outcome.time_to_mfe_sessions == 2
    assert outcome.time_to_mae_sessions == 0
    assert outcome.extreme_order is ExtremeOrder.MAE_BEFORE_MFE
    assert outcome.entry_gap_return == pytest.approx(-0.05)
    assert outcome.max_gap_up_return == pytest.approx(102.0 / 101.0 - 1.0)
    assert outcome.max_gap_down_return == pytest.approx(-0.05)
    assert outcome.max_drawdown_lower_bound == pytest.approx(94.0 / 103.0 - 1.0)
    assert outcome.max_drawdown_upper_bound == pytest.approx(99.0 / 105.0 - 1.0)
    assert outcome.intraday_drawdown_ambiguous is True


def test_end_of_data_is_retained_as_explicit_truncation() -> None:
    bars = (
        _bar(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _bar(1, open_=101.0, high=103.0, low=100.0, close=102.0),
        _bar(2, open_=102.0, high=104.0, low=101.0, close=103.0),
    )

    outcome = measure_outcome_paths(bars, (_event(bars, 1),), horizons=(5,))[0]

    assert outcome.status is OutcomePathStatus.TRUNCATED_END_OF_DATA
    assert outcome.observed_sessions == 1
    assert outcome.forward_return is None
    assert outcome.partial_return == pytest.approx(103.0 / 102.0 - 1.0)
    assert outcome.last_observed_date == bars[2].trade_date


def test_unusable_bar_truncates_before_bad_session() -> None:
    original = (
        _bar(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _bar(1, open_=101.0, high=103.0, low=100.0, close=102.0),
        _bar(2, open_=102.0, high=104.0, low=101.0, close=103.0),
        _bar(3, open_=103.0, high=105.0, low=102.0, close=104.0),
        _bar(4, open_=104.0, high=106.0, low=103.0, close=105.0),
    )
    bars = (
        *original[:3],
        replace(original[3], quality_status=QualityStatus.QUARANTINE),
        original[4],
    )

    outcome = measure_outcome_paths(bars, (_event(bars, 0),), horizons=(4,))[0]

    assert outcome.status is OutcomePathStatus.TRUNCATED_UNUSABLE_BAR
    assert outcome.observed_sessions == 2
    assert outcome.truncation_date == bars[3].trade_date
    assert outcome.forward_return is None
    assert outcome.last_observed_date == bars[2].trade_date


def test_event_on_last_bar_retains_no_entry_status() -> None:
    bars = (
        _bar(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _bar(1, open_=101.0, high=103.0, low=100.0, close=102.0),
    )

    outcome = measure_outcome_paths(bars, (_event(bars, 1),), horizons=(1,))[0]

    assert outcome.status is OutcomePathStatus.NO_ENTRY_BAR
    assert outcome.observed_sessions == 0
    assert outcome.entry_price is None


def test_event_provenance_mismatch_fails_closed() -> None:
    bars = (
        _bar(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _bar(1, open_=101.0, high=103.0, low=100.0, close=102.0),
    )
    event = replace(_event(bars, 0), dataset_version="wrong-dataset")

    with pytest.raises(ValueError, match="dataset version"):
        measure_outcome_paths(bars, (event,), horizons=(1,))
