"""Minimal point-in-time feature additions required by the strategy-suite library.

These primitives remain strategy-neutral.  They add only measurements that the live feature
catalog does not currently expose directly: Keltner-channel state, trailing Bollinger-bandwidth
percentile, and narrow-range (NR-N) state.  No entry, exit, or profitability decision is embedded
in this module.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import pstdev
from types import MappingProxyType

from trade_scout.data.contracts import DailyBar, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus, FeatureValue

STRATEGY_PRIMITIVES_FEATURE_SET_VERSION = "strategy-primitives-v0.1"


class StrategyPrimitiveFamily(StrEnum):
    """Additional neutral measurements required by the first strategy-suite catalog."""

    KELTNER_CHANNEL = "keltner_channel"
    BB_BANDWIDTH_PERCENTILE = "bb_bandwidth_percentile"
    NARROW_RANGE = "narrow_range"


class StrategyPrimitiveMetric(StrEnum):
    """Materialized outputs exposed by the additional primitive families."""

    KC_UPPER_DISTANCE_PCT = "kc_upper_distance_pct"
    KC_LOWER_DISTANCE_PCT = "kc_lower_distance_pct"
    KC_BANDWIDTH_PCT = "kc_bandwidth_pct"
    KC_POSITION = "kc_position"
    KC_UPPER_CROSS_UP = "kc_upper_cross_up"
    KC_LOWER_CROSS_DOWN = "kc_lower_cross_down"
    BB_BANDWIDTH_PERCENTILE = "bb_bandwidth_percentile"
    NARROW_RANGE_FLAG = "narrow_range_flag"


_METRICS_BY_FAMILY: dict[StrategyPrimitiveFamily, frozenset[StrategyPrimitiveMetric]] = {
    StrategyPrimitiveFamily.KELTNER_CHANNEL: frozenset(
        {
            StrategyPrimitiveMetric.KC_UPPER_DISTANCE_PCT,
            StrategyPrimitiveMetric.KC_LOWER_DISTANCE_PCT,
            StrategyPrimitiveMetric.KC_BANDWIDTH_PCT,
            StrategyPrimitiveMetric.KC_POSITION,
            StrategyPrimitiveMetric.KC_UPPER_CROSS_UP,
            StrategyPrimitiveMetric.KC_LOWER_CROSS_DOWN,
        }
    ),
    StrategyPrimitiveFamily.BB_BANDWIDTH_PERCENTILE: frozenset(
        {StrategyPrimitiveMetric.BB_BANDWIDTH_PERCENTILE}
    ),
    StrategyPrimitiveFamily.NARROW_RANGE: frozenset(
        {StrategyPrimitiveMetric.NARROW_RANGE_FLAG}
    ),
}

_BINARY_METRICS = frozenset(
    {
        StrategyPrimitiveMetric.KC_UPPER_CROSS_UP,
        StrategyPrimitiveMetric.KC_LOWER_CROSS_DOWN,
        StrategyPrimitiveMetric.NARROW_RANGE_FLAG,
    }
)


@dataclass(frozen=True, slots=True)
class StrategyPrimitiveSpec:
    """One fully resolved additional feature requested by a research suite."""

    family: StrategyPrimitiveFamily
    metric: StrategyPrimitiveMetric
    period: int = 20
    multiplier: float = 2.0
    rank_period: int = 120
    standard_deviations: float = 2.0

    def __post_init__(self) -> None:
        if self.metric not in _METRICS_BY_FAMILY[self.family]:
            raise ValueError(f"{self.metric.value} is not valid for {self.family.value}")
        if not 2 <= self.period <= 1000:
            raise ValueError("primitive period must be between 2 and 1000 sessions")
        if not math.isfinite(self.multiplier) or not 0.01 <= self.multiplier <= 20:
            raise ValueError("Keltner multiplier must be between 0.01 and 20")
        if not 2 <= self.rank_period <= 2000:
            raise ValueError("rank period must be between 2 and 2000 sessions")
        if (
            not math.isfinite(self.standard_deviations)
            or not 0.01 <= self.standard_deviations <= 20
        ):
            raise ValueError("Bollinger standard deviations must be between 0.01 and 20")

    @property
    def minimum_observations(self) -> int:
        if self.family is StrategyPrimitiveFamily.BB_BANDWIDTH_PERCENTILE:
            return self.period + self.rank_period - 1
        if self.family is StrategyPrimitiveFamily.KELTNER_CHANNEL:
            base = self.period + 1
            return base + 1 if self.metric in _BINARY_METRICS else base
        return self.period

    @property
    def feature_name(self) -> str:
        if self.family is StrategyPrimitiveFamily.KELTNER_CHANNEL:
            return (
                f"sp__{self.metric.value}__p{self.period}__"
                f"m{_number_token(self.multiplier)}"
            )
        if self.family is StrategyPrimitiveFamily.BB_BANDWIDTH_PERCENTILE:
            return (
                f"sp__bb_bandwidth_percentile__p{self.period}__"
                f"k{_number_token(self.standard_deviations)}__r{self.rank_period}"
            )
        return f"sp__nr{self.period}"

    @property
    def units(self) -> str:
        if self.metric in _BINARY_METRICS:
            return "binary"
        if self.metric is StrategyPrimitiveMetric.KC_POSITION:
            return "ratio"
        if self.metric is StrategyPrimitiveMetric.BB_BANDWIDTH_PERCENTILE:
            return "percentile_0_100"
        return "percent"

    @property
    def resolved_parameters(self) -> MappingProxyType[str, str | int | float | bool]:
        values: dict[str, str | int | float | bool] = {
            "family": self.family.value,
            "metric": self.metric.value,
            "period": self.period,
            "timeframe": "daily",
        }
        if self.family is StrategyPrimitiveFamily.KELTNER_CHANNEL:
            values.update(
                center="ema",
                atr_smoothing="wilder",
                multiplier=self.multiplier,
            )
        elif self.family is StrategyPrimitiveFamily.BB_BANDWIDTH_PERCENTILE:
            values.update(
                middle_average="sma",
                standard_deviations=self.standard_deviations,
                dispersion="population_standard_deviation",
                rank_period=self.rank_period,
                rank_window="trailing_including_current",
            )
        else:
            values.update(
                range_definition="split_adjusted_high_minus_low",
                comparison="strictly_less_than_previous_ranges",
            )
        return MappingProxyType(values)


def compute_strategy_primitive_frame(
    bars: Iterable[DailyBar],
    specs: Iterable[StrategyPrimitiveSpec],
) -> tuple[FeatureValue, ...]:
    """Materialize requested primitives from PASS canonical daily bars."""

    materialized = tuple(bars)
    requested = tuple(dict.fromkeys(specs))
    if not materialized:
        raise ValueError("strategy primitives require canonical daily bars")
    if not requested:
        return ()
    if len({item.dataset_version for item in materialized}) != 1:
        raise ValueError("strategy primitives cannot mix canonical dataset versions")
    if any(item.quality_status is not QualityStatus.PASS for item in materialized):
        raise ValueError("strategy primitives require PASS canonical input")

    by_instrument: dict[str, list[DailyBar]] = {}
    seen: set[tuple[str, object]] = set()
    for bar in materialized:
        key = (str(bar.instrument_id), bar.trade_date)
        if key in seen:
            raise ValueError(f"duplicate canonical instrument/date for strategy primitive: {key}")
        seen.add(key)
        by_instrument.setdefault(str(bar.instrument_id), []).append(bar)

    values: list[FeatureValue] = []
    for rows in by_instrument.values():
        ordered = tuple(sorted(rows, key=lambda item: item.trade_date))
        for spec in requested:
            series = _series_for_spec(ordered, spec)
            for index, bar in enumerate(ordered):
                value = series[index]
                status = (
                    FeatureAvailabilityStatus.WARMUP
                    if index + 1 < spec.minimum_observations
                    else FeatureAvailabilityStatus.AVAILABLE
                    if value is not None
                    else FeatureAvailabilityStatus.INPUT_UNAVAILABLE
                )
                values.append(
                    FeatureValue(
                        instrument_id=bar.instrument_id,
                        trade_date=bar.trade_date,
                        feature_name=spec.feature_name,
                        feature_version="v0.1",
                        resolved_parameters=spec.resolved_parameters,
                        value=value if status is FeatureAvailabilityStatus.AVAILABLE else None,
                        units=spec.units,
                        availability_status=status,
                        dataset_version=bar.dataset_version,
                        feature_set_version=STRATEGY_PRIMITIVES_FEATURE_SET_VERSION,
                    )
                )
    return tuple(
        sorted(values, key=lambda item: (str(item.instrument_id), item.trade_date, item.feature_name))
    )


def _series_for_spec(
    bars: tuple[DailyBar, ...], spec: StrategyPrimitiveSpec
) -> tuple[float | None, ...]:
    if spec.family is StrategyPrimitiveFamily.KELTNER_CHANNEL:
        return _keltner_metric(bars, spec)
    if spec.family is StrategyPrimitiveFamily.BB_BANDWIDTH_PERCENTILE:
        return _bb_bandwidth_percentile(bars, spec)
    return _narrow_range(bars, spec.period)


def _keltner_metric(
    bars: tuple[DailyBar, ...], spec: StrategyPrimitiveSpec
) -> tuple[float | None, ...]:
    closes = tuple(_split_close(item) for item in bars)
    center = _ema_series(closes, spec.period)
    atr = _atr_wilder(bars, spec.period)
    upper: list[float | None] = [None] * len(bars)
    lower: list[float | None] = [None] * len(bars)
    for index, (middle, atr_value) in enumerate(zip(center, atr, strict=True)):
        if middle is not None and atr_value is not None:
            upper[index] = middle + spec.multiplier * atr_value
            lower[index] = middle - spec.multiplier * atr_value

    result: list[float | None] = [None] * len(bars)
    for index, close in enumerate(closes):
        middle, top, bottom = center[index], upper[index], lower[index]
        if close is None or close <= 0 or middle is None or top is None or bottom is None:
            continue
        if spec.metric is StrategyPrimitiveMetric.KC_UPPER_DISTANCE_PCT:
            result[index] = (close / top - 1.0) * 100.0
        elif spec.metric is StrategyPrimitiveMetric.KC_LOWER_DISTANCE_PCT:
            result[index] = (close / bottom - 1.0) * 100.0 if bottom > 0 else None
        elif spec.metric is StrategyPrimitiveMetric.KC_BANDWIDTH_PCT:
            result[index] = (top - bottom) / middle * 100.0 if middle > 0 else None
        elif spec.metric is StrategyPrimitiveMetric.KC_POSITION:
            width = top - bottom
            result[index] = (close - bottom) / width if width > 0 else None
        elif index > 0:
            prior_close = closes[index - 1]
            prior_top, prior_bottom = upper[index - 1], lower[index - 1]
            if prior_close is None or prior_top is None or prior_bottom is None:
                continue
            if spec.metric is StrategyPrimitiveMetric.KC_UPPER_CROSS_UP:
                result[index] = float(close > top and prior_close <= prior_top)
            else:
                result[index] = float(close < bottom and prior_close >= prior_bottom)
    return tuple(result)


def _bb_bandwidth_percentile(
    bars: tuple[DailyBar, ...], spec: StrategyPrimitiveSpec
) -> tuple[float | None, ...]:
    closes = tuple(_split_close(item) for item in bars)
    bandwidth: list[float | None] = [None] * len(bars)
    for index in range(spec.period - 1, len(bars)):
        window = closes[index - spec.period + 1 : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        middle = math.fsum(numeric) / spec.period
        if middle <= 0:
            continue
        deviation = pstdev(numeric)
        top = middle + spec.standard_deviations * deviation
        bottom = middle - spec.standard_deviations * deviation
        bandwidth[index] = (top - bottom) / middle * 100.0

    result: list[float | None] = [None] * len(bars)
    first = spec.period + spec.rank_period - 2
    for index in range(first, len(bars)):
        trailing = bandwidth[index - spec.rank_period + 1 : index + 1]
        current = bandwidth[index]
        if current is None or any(value is None for value in trailing):
            continue
        numeric = [float(value) for value in trailing if value is not None]
        result[index] = 100.0 * sum(value <= current for value in numeric) / len(numeric)
    return tuple(result)


def _narrow_range(bars: tuple[DailyBar, ...], period: int) -> tuple[float | None, ...]:
    ranges: list[float | None] = []
    for bar in bars:
        high, low = _split_high(bar), _split_low(bar)
        ranges.append(None if high is None or low is None else high - low)
    result: list[float | None] = [None] * len(bars)
    for index in range(period - 1, len(bars)):
        current = ranges[index]
        previous = ranges[index - period + 1 : index]
        if current is None or any(value is None for value in previous):
            continue
        result[index] = float(all(current < float(value) for value in previous if value is not None))
    return tuple(result)


def _atr_wilder(bars: tuple[DailyBar, ...], period: int) -> tuple[float | None, ...]:
    true_ranges: list[float | None] = [None] * len(bars)
    for index in range(1, len(bars)):
        high, low = _split_high(bars[index]), _split_low(bars[index])
        previous_close = _split_close(bars[index - 1])
        if high is None or low is None or previous_close is None:
            continue
        true_ranges[index] = max(high - low, abs(high - previous_close), abs(low - previous_close))
    result: list[float | None] = [None] * len(bars)
    if len(bars) <= period:
        return tuple(result)
    seed = true_ranges[1 : period + 1]
    if any(value is None for value in seed):
        return tuple(result)
    average = math.fsum(float(value) for value in seed if value is not None) / period
    result[period] = average
    for index in range(period + 1, len(bars)):
        current = true_ranges[index]
        if current is None:
            return tuple(result)
        average = (average * (period - 1) + current) / period
        result[index] = average
    return tuple(result)


def _ema_series(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    seed = values[:period]
    if any(value is None for value in seed):
        return tuple(result)
    ema = math.fsum(float(value) for value in seed if value is not None) / period
    result[period - 1] = ema
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        value = values[index]
        if value is None:
            return tuple(result)
        ema = alpha * value + (1.0 - alpha) * ema
        result[index] = ema
    return tuple(result)


def _split_open(bar: DailyBar) -> float | None:
    return _finite_positive(bar.open_split_adjusted)


def _split_high(bar: DailyBar) -> float | None:
    return _finite_positive(bar.high_split_adjusted)


def _split_low(bar: DailyBar) -> float | None:
    return _finite_positive(bar.low_split_adjusted)


def _split_close(bar: DailyBar) -> float | None:
    return _finite_positive(bar.close_split_adjusted)


def _finite_positive(value: float | None) -> float | None:
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _number_token(value: float) -> str:
    return format(value, ".6g").replace("-", "m").replace(".", "p")


__all__ = [
    "STRATEGY_PRIMITIVES_FEATURE_SET_VERSION",
    "StrategyPrimitiveFamily",
    "StrategyPrimitiveMetric",
    "StrategyPrimitiveSpec",
    "compute_strategy_primitive_frame",
]
