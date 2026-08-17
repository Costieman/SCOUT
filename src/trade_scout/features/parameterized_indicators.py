"""Operator-parameterized point-in-time technical indicators for strategy composition.

The visual research workbench should expose familiar technical-analysis concepts rather than a
collection of hard-coded feature instances.  This module therefore materializes resolved indicator
specifications from immutable daily canonical bars.  Every feature is point-in-time, deterministic,
and provider-neutral.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from statistics import pstdev, stdev
from types import MappingProxyType

from trade_scout.data.contracts import DailyBar, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus, FeatureValue

PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION = "parameterized-indicators-v0.2"


class IndicatorFamily(StrEnum):
    """Technical-indicator families available to the visual strategy composer."""

    MOVING_AVERAGE = "moving_average"
    BOLLINGER_BANDS = "bollinger_bands"
    PRICE_ROC = "price_roc"
    RSI = "rsi"
    MACD = "macd"
    ATR = "atr"
    RELATIVE_VOLUME = "relative_volume"
    AVERAGE_DOLLAR_VOLUME = "average_dollar_volume"
    HISTORICAL_VOLATILITY = "historical_volatility"
    PRIOR_HIGH = "prior_high"


class MovingAverageType(StrEnum):
    SMA = "sma"
    EMA = "ema"


class PriceSource(StrEnum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"


class IndicatorMetric(StrEnum):
    MA_DISTANCE_PCT = "ma_distance_pct"
    MA_CROSS_UP = "ma_cross_up"
    MA_CROSS_DOWN = "ma_cross_down"
    BB_UPPER_DISTANCE_PCT = "bb_upper_distance_pct"
    BB_MIDDLE_DISTANCE_PCT = "bb_middle_distance_pct"
    BB_LOWER_DISTANCE_PCT = "bb_lower_distance_pct"
    BB_UPPER_REACHED = "bb_upper_reached"
    BB_LOWER_REACHED = "bb_lower_reached"
    BB_UPPER_CROSS_UP = "bb_upper_cross_up"
    BB_LOWER_CROSS_DOWN = "bb_lower_cross_down"
    BB_MIDDLE_CROSS_UP = "bb_middle_cross_up"
    BB_MIDDLE_CROSS_DOWN = "bb_middle_cross_down"
    BB_BANDWIDTH_PCT = "bb_bandwidth_pct"
    BB_POSITION = "bb_position"
    ROC_PCT = "roc_pct"
    RSI_VALUE = "rsi_value"
    MACD_LINE_PCT = "macd_line_pct"
    MACD_SIGNAL_PCT = "macd_signal_pct"
    MACD_HISTOGRAM_PCT = "macd_histogram_pct"
    MACD_CROSS_UP = "macd_cross_up"
    MACD_CROSS_DOWN = "macd_cross_down"
    ATR_PCT = "atr_pct"
    RVOL = "rvol"
    AVERAGE_DOLLAR_VOLUME = "average_dollar_volume"
    HISTORICAL_VOLATILITY_PCT = "historical_volatility_pct"
    PRIOR_HIGH_DISTANCE_PCT = "prior_high_distance_pct"
    PRIOR_HIGH_BREAKOUT = "prior_high_breakout"


_METRICS_BY_FAMILY: dict[IndicatorFamily, frozenset[IndicatorMetric]] = {
    IndicatorFamily.MOVING_AVERAGE: frozenset(
        {
            IndicatorMetric.MA_DISTANCE_PCT,
            IndicatorMetric.MA_CROSS_UP,
            IndicatorMetric.MA_CROSS_DOWN,
        }
    ),
    IndicatorFamily.BOLLINGER_BANDS: frozenset(
        {
            IndicatorMetric.BB_UPPER_DISTANCE_PCT,
            IndicatorMetric.BB_MIDDLE_DISTANCE_PCT,
            IndicatorMetric.BB_LOWER_DISTANCE_PCT,
            IndicatorMetric.BB_UPPER_REACHED,
            IndicatorMetric.BB_LOWER_REACHED,
            IndicatorMetric.BB_UPPER_CROSS_UP,
            IndicatorMetric.BB_LOWER_CROSS_DOWN,
            IndicatorMetric.BB_MIDDLE_CROSS_UP,
            IndicatorMetric.BB_MIDDLE_CROSS_DOWN,
            IndicatorMetric.BB_BANDWIDTH_PCT,
            IndicatorMetric.BB_POSITION,
        }
    ),
    IndicatorFamily.PRICE_ROC: frozenset({IndicatorMetric.ROC_PCT}),
    IndicatorFamily.RSI: frozenset({IndicatorMetric.RSI_VALUE}),
    IndicatorFamily.MACD: frozenset(
        {
            IndicatorMetric.MACD_LINE_PCT,
            IndicatorMetric.MACD_SIGNAL_PCT,
            IndicatorMetric.MACD_HISTOGRAM_PCT,
            IndicatorMetric.MACD_CROSS_UP,
            IndicatorMetric.MACD_CROSS_DOWN,
        }
    ),
    IndicatorFamily.ATR: frozenset({IndicatorMetric.ATR_PCT}),
    IndicatorFamily.RELATIVE_VOLUME: frozenset({IndicatorMetric.RVOL}),
    IndicatorFamily.AVERAGE_DOLLAR_VOLUME: frozenset({IndicatorMetric.AVERAGE_DOLLAR_VOLUME}),
    IndicatorFamily.HISTORICAL_VOLATILITY: frozenset({IndicatorMetric.HISTORICAL_VOLATILITY_PCT}),
    IndicatorFamily.PRIOR_HIGH: frozenset(
        {IndicatorMetric.PRIOR_HIGH_DISTANCE_PCT, IndicatorMetric.PRIOR_HIGH_BREAKOUT}
    ),
}

_BINARY_METRICS = frozenset(
    {
        IndicatorMetric.MA_CROSS_UP,
        IndicatorMetric.MA_CROSS_DOWN,
        IndicatorMetric.BB_UPPER_REACHED,
        IndicatorMetric.BB_LOWER_REACHED,
        IndicatorMetric.BB_UPPER_CROSS_UP,
        IndicatorMetric.BB_LOWER_CROSS_DOWN,
        IndicatorMetric.BB_MIDDLE_CROSS_UP,
        IndicatorMetric.BB_MIDDLE_CROSS_DOWN,
        IndicatorMetric.MACD_CROSS_UP,
        IndicatorMetric.MACD_CROSS_DOWN,
        IndicatorMetric.PRIOR_HIGH_BREAKOUT,
    }
)


@dataclass(frozen=True, slots=True)
class ParameterizedIndicatorSpec:
    """One fully resolved technical-indicator output requested by the operator."""

    family: IndicatorFamily
    metric: IndicatorMetric
    period: int
    source: PriceSource = PriceSource.CLOSE
    moving_average_type: MovingAverageType = MovingAverageType.SMA
    standard_deviations: float = 2.0
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    def __post_init__(self) -> None:
        if not 2 <= self.period <= 1000:
            raise ValueError("indicator period must be between 2 and 1000 daily sessions")
        if self.metric not in _METRICS_BY_FAMILY[self.family]:
            raise ValueError(f"{self.metric.value} is not valid for {self.family.value}")
        if (
            not math.isfinite(self.standard_deviations)
            or not 0.01 <= self.standard_deviations <= 20
        ):
            raise ValueError("Bollinger standard deviations must be between 0.01 and 20")
        if not 2 <= self.fast_period < self.slow_period <= 1000:
            raise ValueError("MACD periods require 2 <= fast < slow <= 1000")
        if not 2 <= self.signal_period <= 1000:
            raise ValueError("MACD signal period must be between 2 and 1000")

    @property
    def feature_name(self) -> str:
        """Return a stable safe identifier encoding all material parameters."""

        prefix = ["pi", self.family.value, self.metric.value, self.source.value, f"p{self.period}"]
        if self.family is IndicatorFamily.MOVING_AVERAGE:
            suffix = self.moving_average_type.value
        elif self.family is IndicatorFamily.BOLLINGER_BANDS:
            suffix = f"k{_number_token(self.standard_deviations)}"
        elif self.family is IndicatorFamily.MACD:
            suffix = f"f{self.fast_period}s{self.slow_period}g{self.signal_period}"
        elif self.family in {IndicatorFamily.RSI, IndicatorFamily.ATR}:
            suffix = "wilder"
        elif self.family is IndicatorFamily.HISTORICAL_VOLATILITY:
            suffix = "annual252"
        elif self.family in {
            IndicatorFamily.RELATIVE_VOLUME,
            IndicatorFamily.AVERAGE_DOLLAR_VOLUME,
            IndicatorFamily.PRIOR_HIGH,
        }:
            suffix = "prior"
        else:
            suffix = "standard"
        return "__".join((*prefix, suffix))

    @property
    def minimum_observations(self) -> int:
        if self.family is IndicatorFamily.MACD:
            base = self.slow_period + self.signal_period - 1
            return base + 1 if self.metric in _BINARY_METRICS else base
        if self.family in {
            IndicatorFamily.PRICE_ROC,
            IndicatorFamily.RELATIVE_VOLUME,
            IndicatorFamily.AVERAGE_DOLLAR_VOLUME,
            IndicatorFamily.HISTORICAL_VOLATILITY,
            IndicatorFamily.PRIOR_HIGH,
        }:
            return self.period + 1
        if self.metric in _BINARY_METRICS:
            return self.period + 1
        if self.family in {IndicatorFamily.RSI, IndicatorFamily.ATR}:
            return self.period + 1
        return self.period

    @property
    def units(self) -> str:
        if self.metric in _BINARY_METRICS:
            return "binary"
        if self.metric is IndicatorMetric.BB_POSITION:
            return "ratio"
        if self.metric is IndicatorMetric.RSI_VALUE:
            return "index_0_100"
        if self.metric is IndicatorMetric.RVOL:
            return "multiple"
        if self.metric is IndicatorMetric.AVERAGE_DOLLAR_VOLUME:
            return "currency_volume"
        return "percent"

    @property
    def resolved_parameters(self) -> MappingProxyType[str, str | int | float | bool]:
        values: dict[str, str | int | float | bool] = {
            "family": self.family.value,
            "metric": self.metric.value,
            "period": self.period,
            "source": self.source.value,
            "timeframe": "daily",
        }
        if self.family is IndicatorFamily.MOVING_AVERAGE:
            values["moving_average_type"] = self.moving_average_type.value
        elif self.family is IndicatorFamily.BOLLINGER_BANDS:
            values.update(
                middle_average="sma",
                standard_deviations=self.standard_deviations,
                dispersion="population_standard_deviation",
            )
        elif self.family is IndicatorFamily.MACD:
            values.update(
                fast_period=self.fast_period,
                slow_period=self.slow_period,
                signal_period=self.signal_period,
                ema_seed="sma",
            )
        elif self.family in {IndicatorFamily.RSI, IndicatorFamily.ATR}:
            values["smoothing"] = "wilder"
        elif self.family is IndicatorFamily.HISTORICAL_VOLATILITY:
            values.update(return_method="log", annualization_sessions=252, dispersion="sample_sd")
        elif self.family in {
            IndicatorFamily.RELATIVE_VOLUME,
            IndicatorFamily.AVERAGE_DOLLAR_VOLUME,
            IndicatorFamily.PRIOR_HIGH,
        }:
            values["current_session_excluded_from_baseline"] = True
        return MappingProxyType(values)


def compute_parameterized_indicator_frame(
    bars: Iterable[DailyBar],
    specs: Iterable[ParameterizedIndicatorSpec],
) -> tuple[FeatureValue, ...]:
    """Materialize requested indicator outputs using information available through each date."""

    materialized = tuple(bars)
    requested = tuple(dict.fromkeys(specs))
    if not materialized:
        raise ValueError("parameterized indicators require canonical daily bars")
    if not requested:
        return ()
    versions = {item.dataset_version for item in materialized}
    if len(versions) != 1:
        raise ValueError("parameterized indicators cannot mix canonical dataset versions")
    if any(item.quality_status is not QualityStatus.PASS for item in materialized):
        raise ValueError("parameterized indicators require PASS canonical input")

    by_instrument: dict[str, list[DailyBar]] = {}
    seen: set[tuple[str, date]] = set()
    for bar in materialized:
        key = (str(bar.instrument_id), bar.trade_date)
        if key in seen:
            raise ValueError(
                f"duplicate canonical instrument/date for parameterized feature: {key}"
            )
        seen.add(key)
        by_instrument.setdefault(str(bar.instrument_id), []).append(bar)

    values: list[FeatureValue] = []
    for rows in by_instrument.values():
        ordered = tuple(sorted(rows, key=lambda item: item.trade_date))
        for spec in requested:
            values.extend(_compute_spec(ordered, spec))
    return tuple(
        sorted(
            values,
            key=lambda item: (str(item.instrument_id), item.trade_date, item.feature_name),
        )
    )


def _compute_spec(
    bars: tuple[DailyBar, ...], spec: ParameterizedIndicatorSpec
) -> list[FeatureValue]:
    source = tuple(_price(item, spec.source) for item in bars)
    calculated = _series_for_spec(bars, source, spec)
    result: list[FeatureValue] = []
    for index, bar in enumerate(bars):
        value = calculated[index]
        status = (
            FeatureAvailabilityStatus.WARMUP
            if index + 1 < spec.minimum_observations
            else FeatureAvailabilityStatus.AVAILABLE
            if value is not None
            else FeatureAvailabilityStatus.INPUT_UNAVAILABLE
        )
        result.append(
            FeatureValue(
                instrument_id=bar.instrument_id,
                trade_date=bar.trade_date,
                feature_name=spec.feature_name,
                feature_version="v0.2",
                resolved_parameters=spec.resolved_parameters,
                value=value if status is FeatureAvailabilityStatus.AVAILABLE else None,
                units=spec.units,
                availability_status=status,
                dataset_version=bar.dataset_version,
                feature_set_version=PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION,
            )
        )
    return result


def _series_for_spec(
    bars: tuple[DailyBar, ...],
    source: tuple[float | None, ...],
    spec: ParameterizedIndicatorSpec,
) -> tuple[float | None, ...]:
    if spec.family is IndicatorFamily.MOVING_AVERAGE:
        return _moving_average_metric(source, spec)
    if spec.family is IndicatorFamily.BOLLINGER_BANDS:
        return _bollinger_metric(bars, source, spec)
    if spec.family is IndicatorFamily.PRICE_ROC:
        return _rate_of_change(source, spec.period)
    if spec.family is IndicatorFamily.RSI:
        return _rsi_wilder(source, spec.period)
    if spec.family is IndicatorFamily.MACD:
        return _macd_metric(source, spec)
    if spec.family is IndicatorFamily.ATR:
        return _atr_percent(bars, spec.period)
    if spec.family is IndicatorFamily.RELATIVE_VOLUME:
        return _relative_volume(bars, spec.period)
    if spec.family is IndicatorFamily.AVERAGE_DOLLAR_VOLUME:
        return _average_dollar_volume(bars, spec.period)
    if spec.family is IndicatorFamily.HISTORICAL_VOLATILITY:
        return _historical_volatility(source, spec.period)
    return _prior_high_metric(bars, source, spec)


def _moving_average_metric(
    source: tuple[float | None, ...], spec: ParameterizedIndicatorSpec
) -> tuple[float | None, ...]:
    average = _moving_average_series(source, spec.period, spec.moving_average_type)
    result: list[float | None] = [None] * len(source)
    for index, (current, middle) in enumerate(zip(source, average, strict=True)):
        if current is None or middle is None or middle <= 0:
            continue
        if spec.metric is IndicatorMetric.MA_DISTANCE_PCT:
            result[index] = (current / middle - 1.0) * 100.0
        elif index > 0 and source[index - 1] is not None and average[index - 1] is not None:
            prior, prior_middle = source[index - 1], average[index - 1]
            assert prior is not None and prior_middle is not None
            if spec.metric is IndicatorMetric.MA_CROSS_UP:
                result[index] = float(current > middle and prior <= prior_middle)
            else:
                result[index] = float(current < middle and prior >= prior_middle)
    return tuple(result)


def _bollinger_metric(
    bars: tuple[DailyBar, ...],
    source: tuple[float | None, ...],
    spec: ParameterizedIndicatorSpec,
) -> tuple[float | None, ...]:
    middle, upper, lower = _bollinger_series(source, spec.period, spec.standard_deviations)
    result: list[float | None] = [None] * len(source)
    for index, current in enumerate(source):
        mid, top, bottom = middle[index], upper[index], lower[index]
        if current is None or mid is None or top is None or bottom is None or mid <= 0:
            continue
        metric = spec.metric
        if metric is IndicatorMetric.BB_UPPER_DISTANCE_PCT:
            result[index] = (current / top - 1.0) * 100.0
        elif metric is IndicatorMetric.BB_MIDDLE_DISTANCE_PCT:
            result[index] = (current / mid - 1.0) * 100.0
        elif metric is IndicatorMetric.BB_LOWER_DISTANCE_PCT:
            result[index] = (current / bottom - 1.0) * 100.0
        elif metric is IndicatorMetric.BB_BANDWIDTH_PCT:
            result[index] = (top - bottom) / mid * 100.0
        elif metric is IndicatorMetric.BB_POSITION:
            width = top - bottom
            result[index] = None if width <= 0 else (current - bottom) / width
        elif metric is IndicatorMetric.BB_UPPER_REACHED:
            high = _split_price(bars[index].high_split_adjusted)
            result[index] = None if high is None else float(high >= top)
        elif metric is IndicatorMetric.BB_LOWER_REACHED:
            low = _split_price(bars[index].low_split_adjusted)
            result[index] = None if low is None else float(low <= bottom)
        elif index > 0:
            previous = source[index - 1]
            previous_mid = middle[index - 1]
            previous_top = upper[index - 1]
            previous_bottom = lower[index - 1]
            if None in {previous, previous_mid, previous_top, previous_bottom}:
                continue
            assert previous is not None and previous_mid is not None
            assert previous_top is not None and previous_bottom is not None
            if metric is IndicatorMetric.BB_UPPER_CROSS_UP:
                result[index] = float(current > top and previous <= previous_top)
            elif metric is IndicatorMetric.BB_LOWER_CROSS_DOWN:
                result[index] = float(current < bottom and previous >= previous_bottom)
            elif metric is IndicatorMetric.BB_MIDDLE_CROSS_UP:
                result[index] = float(current > mid and previous <= previous_mid)
            else:
                result[index] = float(current < mid and previous >= previous_mid)
    return tuple(result)


def _rate_of_change(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        current, prior = values[index], values[index - period]
        if current is not None and prior is not None and prior > 0:
            result[index] = (current / prior - 1.0) * 100.0
    return tuple(result)


def _rsi_wilder(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return tuple(result)
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        if values[index] is None or values[index - 1] is None:
            return tuple(result)
        change = float(values[index]) - float(values[index - 1])
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = math.fsum(gains) / period
    avg_loss = math.fsum(losses) / period
    result[period] = _rsi_value(avg_gain, avg_loss)
    for index in range(period + 1, len(values)):
        if values[index] is None or values[index - 1] is None:
            return tuple(result)
        change = float(values[index]) - float(values[index - 1])
        gain, loss = max(change, 0.0), max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        result[index] = _rsi_value(avg_gain, avg_loss)
    return tuple(result)


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _macd_metric(
    source: Sequence[float | None], spec: ParameterizedIndicatorSpec
) -> tuple[float | None, ...]:
    fast = _ema_series(source, spec.fast_period)
    slow = _ema_series(source, spec.slow_period)
    macd: list[float | None] = [None] * len(source)
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow, strict=True)):
        if fast_value is not None and slow_value is not None:
            macd[index] = fast_value - slow_value
    signal = _ema_series_with_gaps(macd, spec.signal_period)
    result: list[float | None] = [None] * len(source)
    for index, current in enumerate(source):
        line, signal_value = macd[index], signal[index]
        if current is None or current <= 0 or line is None:
            continue
        if spec.metric is IndicatorMetric.MACD_LINE_PCT:
            result[index] = line / current * 100.0
        elif signal_value is not None and spec.metric is IndicatorMetric.MACD_SIGNAL_PCT:
            result[index] = signal_value / current * 100.0
        elif signal_value is not None and spec.metric is IndicatorMetric.MACD_HISTOGRAM_PCT:
            result[index] = (line - signal_value) / current * 100.0
        elif signal_value is not None and index > 0:
            prior_line, prior_signal = macd[index - 1], signal[index - 1]
            if prior_line is None or prior_signal is None:
                continue
            if spec.metric is IndicatorMetric.MACD_CROSS_UP:
                result[index] = float(line > signal_value and prior_line <= prior_signal)
            elif spec.metric is IndicatorMetric.MACD_CROSS_DOWN:
                result[index] = float(line < signal_value and prior_line >= prior_signal)
    return tuple(result)


def _atr_percent(bars: tuple[DailyBar, ...], period: int) -> tuple[float | None, ...]:
    true_ranges: list[float | None] = [None] * len(bars)
    for index in range(1, len(bars)):
        high = _split_price(bars[index].high_split_adjusted)
        low = _split_price(bars[index].low_split_adjusted)
        previous_close = _split_price(bars[index - 1].close_split_adjusted)
        if high is None or low is None or previous_close is None:
            continue
        true_ranges[index] = max(high - low, abs(high - previous_close), abs(low - previous_close))
    smoothed = _wilder_series(true_ranges, period)
    result: list[float | None] = [None] * len(bars)
    for index, atr in enumerate(smoothed):
        close = _split_price(bars[index].close_split_adjusted)
        if atr is not None and close is not None and close > 0:
            result[index] = atr / close * 100.0
    return tuple(result)


def _relative_volume(bars: tuple[DailyBar, ...], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(bars)
    for index in range(period, len(bars)):
        prior = tuple(item.volume_raw for item in bars[index - period : index])
        current = bars[index].volume_raw
        if current is None or any(item is None for item in prior):
            continue
        baseline = math.fsum(float(item) for item in prior if item is not None) / period
        if baseline > 0:
            result[index] = float(current) / baseline
    return tuple(result)


def _average_dollar_volume(bars: tuple[DailyBar, ...], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(bars)
    for index in range(period, len(bars)):
        values: list[float] = []
        for bar in bars[index - period : index]:
            if bar.close_raw is None or bar.volume_raw is None:
                values = []
                break
            values.append(float(bar.close_raw) * float(bar.volume_raw))
        if values:
            result[index] = math.fsum(values) / period
    return tuple(result)


def _historical_volatility(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        window = values[index - period : index + 1]
        if any(item is None or item <= 0 for item in window):
            continue
        logs = [math.log(float(window[i]) / float(window[i - 1])) for i in range(1, len(window))]
        if len(logs) >= 2:
            result[index] = stdev(logs) * math.sqrt(252.0) * 100.0
    return tuple(result)


def _prior_high_metric(
    bars: tuple[DailyBar, ...],
    source: Sequence[float | None],
    spec: ParameterizedIndicatorSpec,
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(bars)
    for index in range(spec.period, len(bars)):
        highs = tuple(
            _split_price(item.high_split_adjusted) for item in bars[index - spec.period : index]
        )
        current = source[index]
        if current is None or any(item is None for item in highs):
            continue
        prior_high = max(float(item) for item in highs if item is not None)
        if spec.metric is IndicatorMetric.PRIOR_HIGH_DISTANCE_PCT:
            result[index] = (current / prior_high - 1.0) * 100.0
        else:
            result[index] = float(current > prior_high)
    return tuple(result)


def _moving_average_series(
    values: Sequence[float | None], period: int, average_type: MovingAverageType
) -> tuple[float | None, ...]:
    if average_type is MovingAverageType.EMA:
        return _ema_series(values, period)
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if any(item is None for item in window):
            continue
        result[index] = math.fsum(float(item) for item in window if item is not None) / period
    return tuple(result)


def _ema_series(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period or any(item is None for item in values[:period]):
        return tuple(result)
    previous = math.fsum(float(item) for item in values[:period] if item is not None) / period
    result[period - 1] = previous
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = values[index]
        if current is None:
            return tuple(result)
        previous = alpha * current + (1.0 - alpha) * previous
        result[index] = previous
    return tuple(result)


def _ema_series_with_gaps(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    first = next((index for index, value in enumerate(values) if value is not None), None)
    if first is None or first + period > len(values):
        return tuple(result)
    seed = values[first : first + period]
    if any(item is None for item in seed):
        return tuple(result)
    previous = math.fsum(float(item) for item in seed if item is not None) / period
    seed_index = first + period - 1
    result[seed_index] = previous
    alpha = 2.0 / (period + 1.0)
    for index in range(seed_index + 1, len(values)):
        current = values[index]
        if current is None:
            return tuple(result)
        previous = alpha * current + (1.0 - alpha) * previous
        result[index] = previous
    return tuple(result)


def _wilder_series(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    first = next((index for index, value in enumerate(values) if value is not None), None)
    if first is None or first + period > len(values):
        return tuple(result)
    seed = values[first : first + period]
    if any(item is None for item in seed):
        return tuple(result)
    previous = math.fsum(float(item) for item in seed if item is not None) / period
    seed_index = first + period - 1
    result[seed_index] = previous
    for index in range(seed_index + 1, len(values)):
        current = values[index]
        if current is None:
            return tuple(result)
        previous = (previous * (period - 1) + current) / period
        result[index] = previous
    return tuple(result)


def _bollinger_series(
    values: Sequence[float | None], period: int, standard_deviations: float
) -> tuple[tuple[float | None, ...], tuple[float | None, ...], tuple[float | None, ...]]:
    middle: list[float | None] = [None] * len(values)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if any(item is None for item in window):
            continue
        numeric = tuple(float(item) for item in window if item is not None)
        mean = math.fsum(numeric) / period
        deviation = pstdev(numeric)
        middle[index] = mean
        upper[index] = mean + standard_deviations * deviation
        lower[index] = mean - standard_deviations * deviation
    return tuple(middle), tuple(upper), tuple(lower)


def _price(bar: DailyBar, source: PriceSource) -> float | None:
    if source is PriceSource.OPEN:
        return _split_price(bar.open_split_adjusted)
    if source is PriceSource.HIGH:
        return _split_price(bar.high_split_adjusted)
    if source is PriceSource.LOW:
        return _split_price(bar.low_split_adjusted)
    return _split_price(bar.close_split_adjusted)


def _split_price(value: float | None) -> float | None:
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _number_token(value: float) -> str:
    return format(value, ".8g").replace("-", "m").replace(".", "p")


__all__ = [
    "PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION",
    "IndicatorFamily",
    "IndicatorMetric",
    "MovingAverageType",
    "ParameterizedIndicatorSpec",
    "PriceSource",
    "compute_parameterized_indicator_frame",
]
