from datetime import timedelta

import pytest

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation
from trade_scout.synthetic import (
    SyntheticAnnotationKind,
    SyntheticScenarioKind,
    ambiguous_daily_bar_scenario,
    clean_trend_scenario,
    gap_down_scenario,
    missing_bars_scenario,
    split_discontinuity_scenario,
    standard_market_laboratory,
    stop_out_scenario,
)


def test_standard_laboratory_contains_every_registered_scenario() -> None:
    laboratory = standard_market_laboratory()

    assert set(laboratory) == set(SyntheticScenarioKind)
    assert len(laboratory) == 10
    assert all(scenario.raw_bars for scenario in laboratory.values())


def test_standard_laboratory_is_deterministic() -> None:
    first = standard_market_laboratory()
    second = standard_market_laboratory()

    assert first == second


def test_every_scenario_has_strictly_increasing_valid_ohlc() -> None:
    for scenario in standard_market_laboratory().values():
        dates = [bar.trade_date for bar in scenario.raw_bars]
        assert dates == sorted(dates)
        assert len(dates) == len(set(dates))
        for bar in scenario.raw_bars:
            assert bar.low <= min(bar.open, bar.close)
            assert bar.high >= max(bar.open, bar.close)
            assert bar.low <= bar.high
            assert bar.volume >= 0
            assert bar.price_representation is PriceRepresentation.RAW


def test_clean_trend_is_monotonic_and_has_only_trend_truth() -> None:
    scenario = clean_trend_scenario()
    closes = [bar.close for bar in scenario.raw_bars]

    assert closes == sorted(closes)
    assert len(scenario.annotations) == 1
    assert scenario.annotations[0].kind is SyntheticAnnotationKind.TREND
    assert scenario.annotations[0].values["direction"] == "up"


def test_missing_bar_annotations_identify_dates_absent_from_history() -> None:
    scenario = missing_bars_scenario()
    observed_dates = {bar.trade_date for bar in scenario.raw_bars}
    missing_dates = {
        annotation.start_date
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.MISSING_BAR
    }

    assert len(missing_dates) == 3
    assert missing_dates.isdisjoint(observed_dates)
    assert any(
        (later - earlier) > timedelta(days=3)
        for earlier, later in zip(
            (bar.trade_date for bar in scenario.raw_bars),
            (bar.trade_date for bar in scenario.raw_bars[1:]),
            strict=False,
        )
    )


def test_split_scenario_carries_raw_and_adjusted_representations() -> None:
    scenario = split_discontinuity_scenario()
    raw = scenario.bars(PriceRepresentation.RAW)
    adjusted = scenario.bars(PriceRepresentation.SPLIT_ADJUSTED)

    assert len(raw) == len(adjusted)
    assert tuple(bar.trade_date for bar in raw) == tuple(bar.trade_date for bar in adjusted)
    assert all(bar.price_representation is PriceRepresentation.SPLIT_ADJUSTED for bar in adjusted)
    assert len(scenario.corporate_actions) == 1
    action = scenario.corporate_actions[0]
    assert action.action_type is CorporateActionType.SPLIT
    assert action.source_fields["split_ratio"] == 2.0

    split_date = action.effective_date
    split_index = next(index for index, bar in enumerate(raw) if bar.trade_date == split_date)
    raw_ratio = raw[split_index].close / raw[split_index - 1].close
    adjusted_ratio = adjusted[split_index].close / adjusted[split_index - 1].close
    assert raw_ratio < 0.6
    assert 0.95 < adjusted_ratio < 1.05


def test_non_split_scenario_rejects_adjusted_request() -> None:
    with pytest.raises(ValueError, match="split-adjusted bars unavailable"):
        clean_trend_scenario().bars(PriceRepresentation.SPLIT_ADJUSTED)


def test_gap_down_encodes_known_overnight_gap() -> None:
    scenario = gap_down_scenario()
    annotation = next(
        item for item in scenario.annotations if item.kind is SyntheticAnnotationKind.GAP_DOWN
    )
    gap_bar = next(bar for bar in scenario.raw_bars if bar.trade_date == annotation.start_date)

    prior_index = scenario.raw_bars.index(gap_bar) - 1
    prior_close = scenario.raw_bars[prior_index].close
    assert gap_bar.open == pytest.approx(prior_close * 0.88)
    assert annotation.values["gap_fraction"] == pytest.approx(-0.12)


def test_stop_out_path_hits_stop_before_recovering_above_entry() -> None:
    scenario = stop_out_scenario()
    annotation = next(
        item for item in scenario.annotations if item.kind is SyntheticAnnotationKind.STOP_HIT
    )
    stop_price = float(annotation.values["stop_price"])
    entry_price = float(annotation.values["entry_price"])
    hit_index = next(
        index
        for index, bar in enumerate(scenario.raw_bars)
        if bar.trade_date == annotation.start_date
    )

    assert scenario.raw_bars[hit_index].low < stop_price
    assert any(bar.close > entry_price for bar in scenario.raw_bars[hit_index + 1 :])


def test_ambiguous_daily_bar_touches_stop_and_target_on_same_session() -> None:
    scenario = ambiguous_daily_bar_scenario()
    annotation = next(
        item for item in scenario.annotations if item.kind is SyntheticAnnotationKind.AMBIGUOUS_BAR
    )
    bar = next(item for item in scenario.raw_bars if item.trade_date == annotation.start_date)
    stop_price = float(annotation.values["stop_price"])
    target_price = float(annotation.values["target_price"])

    assert bar.low <= stop_price
    assert bar.high >= target_price
    assert bar.low < bar.open < bar.high
