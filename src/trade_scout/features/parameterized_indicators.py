"""Parameterized point-in-time technical indicators for visual strategy composition.

Unlike the fixed convenience feature pack, this module materializes operator-requested indicator
instances with explicit parameters. Generated feature names are deterministic and safe for the
existing restricted expression engine. No provider or strategy-specific logic lives here.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import pstdev
from types import MappingProxyType

from trade_scout.data.contracts import DailyBar, PriceRepresentation, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus, FeatureValue

PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION = "parameterized-indicators-v0.1"


class IndicatorFamily(StrEnum):
    MOVING_AVERAGE = "moving_average"
    BOLLINGER_BANDS = "bollinger_bands"


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


_MA_METRICS = frozenset(
    {
        IndicatorMetric.MA_DISTANCE_PCT,
        IndicatorMetric.MA_CROSS_UP,
        IndicatorMetric.MA_CROSS_DOWN,
    }
)
_BB_METRICS = frozenset(set(IndicatorMetric) - _MA_METRICS)


@dataclass(frozen=True, slots=True)
class ParameterizedIndicatorSpec:
    """One fully resolved indicator instance and requested output metric."""

    family: IndicatorFamily
    metric: IndicatorMetric
    period: int
    source: PriceSource = PriceSource.CLOSE
    moving_average_type: MovingAverageType = MovingAverageType.SMA
    standard_deviations: float = 2.0

    def __post_init__(self) -> None:
        if not 2 <= self.period <= 1000:
            raise ValueError("indicator period must be between 2 and 1000 sessions")
        if not math.isfinite(self.standard_deviations) or not 0.01 <= self.standard_deviations <= 20:
            raise ValueError("Bollinger standard deviations must be between 0.01 and 20")
        if self.family is IndicatorFamily.MOVING_AVERAGE and self.metric not in _MA_METRICS:
            raise ValueError("moving-average family requires a moving-average metric")
        if self.family is IndicatorFamily.BOLLINGER_BANDS and self.metric not in _BB_METRICS:
            raise ValueError("Bollinger family requires a Bollinger metric")

    @property
    def feature_name(self) -> str:
        """Return a deterministic safe identifier for this materialized feature."""

        parts = [
            "pi",
            self.family.value,
            self.metric.value,
            self.source.value,
            f"p{self.period}",
        ]
        if self.family is IndicatorFamily.MOVING_AVERAGE:
            parts.append(self.moving_average_type.value)
        else:
            parts.append(f"k{_number_token(self.standard_deviations)}")
        return "__".join(parts)

    @property
    def minimum_observations(self) -> int:
        if self.metric in {
            IndicatorMetric.MA_CROSS_UP,
            IndicatorMetric.MA_CROSS_DOWN,
            IndicatorMetric.BB_UPPER_CROSS_UP,
            IndicatorMetric.BB_LOWER_CROSS_DOWN,
            IndicatorMetric.BB_MIDDLE_CROSS_UP,
            IndicatorMetric.BB_MIDDLE_CROSS_DOWN,
        }:
            return self.period + 1
        return self.period

    @property
    def units(self) -> str:
        if self.metric in {
            IndicatorMetric.MA_CROSS_UP,
            IndicatorMetric.MA_CROSS_DOWN,
            IndicatorMetric.BB_UPPER_REACHED,
            IndicatorMetric.BB_LOWER_REACHED,
            IndicatorMetric.BB_UPPER_CROSS_UP,
            IndicatorMetric.BB_LOWER_CROSS_DOWN,
            IndicatorMetric.BB_MIDDLE_CROSS_UP,
            IndicatorMetric.BB_MIDDLE_CROSS_DOWN,
        }:
            return "binary"
        if self.metric is IndicatorMetric.BB_POSITION:
            return "ratio"
        return "percent"

    @property
    def resolved_parameters(self) -> MappingProxyType[str, str | int | float | bool]:
        values: dict[str, str | int | float | bool] = {
            "family": self.family.value,
            "metric": self.metric.value,
            "period": self.period,
            "source": self.source.value,
        }
        if self.family is IndicatorFamily.MOVING_AVERAGE:
            values["moving_average_type"] = self.moving_average_type.value
        else:
            values["middle_average"] = "sma"
            values["standard_deviations"] = self.standard_deviations
            values["dispersion"] = "population_standard_deviation"
        return MappingProxyType(values)


def compute_parameterized_indicator_frame(
    bars: Iterable[DailyBar],
    specs: Iterable[ParameterizedIndicatorSpec],
) -> tuple[FeatureValue, ...]:
    """Materialize requested indicator metrics using information available through each session t."""

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
    seen: set[tuple[str, object]] = set()
    for bar in materialized:
        key = (str(bar.instrument_id), bar.trade_date)
        if key in seen:
            raise ValueError(f"duplicate canonical instrument/date for parameterized feature: {key}")
        seen.add(key)
        by_instrument.setdefault(str(bar.instrument_id), []).append(bar)

    values: list[FeatureValue] = []
    for instrument_bars in by_instrument.values():
        ordered = tuple(sorted(instrument_bars, key=lambda item: item.trade_date))
        for spec in requested:
            values.extend(_compute_spec(ordered, spec))
    return tuple(
        sorted(
            values,
            key=lambda item: (str(item.instrument_id), item.trade_date, item.feature_name),
        )
    )


def _compute_spec(
    bars: tuple[DailyBar, ...],
    spec: ParameterizedIndicatorSpec,
) -> list[FeatureValue]:
    source = tuple(_price(item, spec.source) for item in bars)
    if spec.family is IndicatorFamily.MOVING_AVERAGE:
        center = _moving_average_series(source, spec.period, spec.moving_average_type)
        upper: tuple[float | None, ...] | None = None
        lower: tuple[float | None, ...] | None = None
    else:
        center, upper, lower = _bollinger_series(source, spec.period, spec.standard_deviations)

    result: list[FeatureValue] = []
    for index, bar in enumerate(bars):
        if index + 1 < spec.minimum_observations:
            status, value = FeatureAvailabilityStatus.WARMUP, None
        else:
            status, value = _value_at(
                bars,
                source,
                center,
                upper,
                lower,
                index=index,
                spec=spec,
            )
        result.append(
            FeatureValue(
                instrument_id=bar.instrument_id,
                trade_date=bar.trade_date,
                feature_name=spec.feature_name,
                feature_version="v0.1",
                resolved_parameters=spec.resolved_parameters,
                value=value,
                units=spec.units,
                availability_status=status,
                dataset_version=bar.dataset_version,
                feature_set_version=PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION,
            )
        )
    return result


def _value_at(
    bars: tuple[DailyBar, ...],
    source: tuple[float | None, ...],
    center: tuple[float | None, ...],
    upper: tuple[float | None, ...] | None,
    lower: tuple[float | None, ...] | None,
    *,
    index: int,
    spec: ParameterizedIndicatorSpec,
) -> tuple[FeatureAvailabilityStatus, float | None]:
    current = source[index]
    middle = center[index]
    if current is None or middle is None or middle <= 0:
        return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None

    if spec.family is IndicatorFamily.MOVING_AVERAGE:
        if spec.metric is IndicatorMetric.MA_DISTANCE_PCT:
            return FeatureAvailabilityStatus.AVAILABLE, (current / middle - 1.0) * 100.0
        prior = source[index - 1]
        prior_middle = center[index - 1]
        if prior is None or prior_middle is None:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        if spec.metric is IndicatorMetric.MA_CROSS_UP:
            crossed = current > middle and prior <= prior_middle
        else:
            crossed = current < middle and prior >= prior_middle
        return FeatureAvailabilityStatus.AVAILABLE, float(crossed)

    if upper is None or lower is None:
        raise AssertionError("Bollinger metrics require upper and lower bands")
    top = upper[index]
    bottom = lower[index]
    if top is None or bottom is None or top <= 0 or bottom <= 0:
        return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
    metric = spec.metric
    if metric is IndicatorMetric.BB_UPPER_DISTANCE_PCT:
        return FeatureAvailabilityStatus.AVAILABLE, (current / top - 1.0) * 100.0
    if metric is IndicatorMetric.BB_MIDDLE_DISTANCE_PCT:
        return FeatureAvailabilityStatus.AVAILABLE, (current / middle - 1.0) * 100.0
    if metric is IndicatorMetric.BB_LOWER_DISTANCE_PCT:
        return FeatureAvailabilityStatus.AVAILABLE, (current / bottom - 1.0) * 100.0
    if metric is IndicatorMetric.BB_BANDWIDTH_PCT:
        return FeatureAvailabilityStatus.AVAILABLE, (top - bottom) / middle * 100.0
    if metric is IndicatorMetric.BB_POSITION:
        width = top - bottom
        if width <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, (current - bottom) / width
    if metric is IndicatorMetric.BB_UPPER_REACHED:
        current_high = _split_price(bars[index].high_split_adjusted)
        if current_high is None:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, float(current_high >= top)
    if metric is IndicatorMetric.BB_LOWER_REACHED:
        current_low = _split_price(bars[index].low_split_adjusted)
        if current_low is None:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, float(current_low <= bottom)

    previous = source[index - 1]
    previous_middle = center[index - 1]
    previous_top = upper[index - 1]
    previous_bottom = lower[index - 1]
    if (
        previous is None
        or previous_middle is None
        or previous_top is None
        or previous_bottom is None
    ):
        return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
    if metric is IndicatorMetric.BB_UPPER_CROSS_UP:
        crossed = current > top and previous <= previous_top
    elif metric is IndicatorMetric.BB_LOWER_CROSS_DOWN:
        crossed = current < bottom and previous >= previous_bottom
    elif metric is IndicatorMetric.BB_MIDDLE_CROSS_UP:
        crossed = current > middle and previous <= previous_middle
    else:
        crossed = current < middle and previous >= previous_middle
    return FeatureAvailabilityStatus.AVAILABLE, float(crossed)


def _moving_average_series(
    values: Sequence[float | None],
    period: int,
    average_type: MovingAverageType,
) -> tuple[float | None, ...]:
    if average_type is MovingAverageType.SMA:
        result: list[float | None] = [None] * len(values)
        for index in range(period - 1, len(values)):
            window = values[index - period + 1 : index + 1]
            if any(item is None for item in window):
                continue
            numeric = tuple(float(item) for item in window if item is not None)
            result[index] = math.fsum(numeric) / period
        return tuple(result)
    return _ema_series(values, period)


def _ema_series(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    seed_window = values[:period]
    if any(item is None for item in seed_window):
        return tuple(result)
    seed_values = tuple(float(item) for item in seed_window if item is not None)
    previous = math.fsum(seed_values) / period
    result[period - 1] = previous
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = values[index]
        if current is None:
            previous = math.nan
            continue
        if not math.isfinite(previous):
            return tuple(result)
        previous = alpha * current + (1.0 - alpha) * previous
        result[index] = previous
    return tuple(result)


def _bollinger_series(
    values: Sequence[float | None],
    period: int,
    standard_deviations: float,
) -> tuple[
    tuple[float | None, ...],
    tuple[float | None, ...],
    tuple[float | None, ...],
]:
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
    "IndicatorFamily",
    "IndicatorMetric",
    "MovingAverageType",
    "PARAMETERIZED_INDICATOR_FEATURE_SET_VERSION",
    "ParameterizedIndicatorSpec",
    "PriceSource",
    "compute_parameterized_indicator_frame",
]
