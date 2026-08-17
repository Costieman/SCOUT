"""Reusable point-in-time market-analysis features for strategy research and charting.

The feature pack is intentionally strategy-neutral. It exposes common momentum, trend, volatility,
volume, breakout, and oscillator building blocks so operators can compose entry hypotheses without
adding a bespoke detector for every idea. Every value is computed from information available by the
end of session t; features that describe a prior range explicitly exclude t from that range.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import stdev
from types import MappingProxyType

from trade_scout.data.contracts import DailyBar, PriceRepresentation, QualityStatus
from trade_scout.features.contracts import (
    FeatureAvailabilityStatus,
    FeatureDefinition,
    FeatureSetDefinition,
    FeatureValue,
)

MARKET_ANALYSIS_FEATURE_SET_VERSION = "market-analysis-features-v0.2"


class MarketAnalysisFeatureInputError(ValueError):
    """Raised when canonical bars cannot safely support the analysis feature pack."""


def _params(**values: str | int | float | bool) -> Mapping[str, str | int | float | bool]:
    return MappingProxyType(values)


MARKET_ANALYSIS_FEATURE_SET = FeatureSetDefinition(
    feature_set_version=MARKET_ANALYSIS_FEATURE_SET_VERSION,
    definitions=(
        FeatureDefinition(
            feature_name="return_5",
            feature_version="v0.1",
            description="Five-interval split-adjusted close return ending at t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(intervals=5),
            units="decimal_return",
            minimum_observations=6,
        ),
        FeatureDefinition(
            feature_name="return_20",
            feature_version="v0.1",
            description="20-interval split-adjusted close return ending at t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(intervals=20),
            units="decimal_return",
            minimum_observations=21,
        ),
        FeatureDefinition(
            feature_name="return_252",
            feature_version="v0.1",
            description="252-interval split-adjusted close return ending at t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(intervals=252),
            units="decimal_return",
            minimum_observations=253,
        ),
        FeatureDefinition(
            feature_name="realized_volatility_20",
            feature_version="v0.1",
            description=(
                "Annualized sample standard deviation of 20 one-session log returns ending at t, "
                "using sqrt(252) annualization."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(
                return_intervals=20,
                return_method="log",
                dispersion="sample_standard_deviation",
                annualization_sessions=252,
            ),
            units="annualized_decimal_volatility",
            minimum_observations=21,
        ),
        FeatureDefinition(
            feature_name="relative_volume_20",
            feature_version="v0.1",
            description=(
                "Current raw volume divided by the arithmetic mean of the prior 20 sessions, "
                "excluding t from the denominator."
            ),
            required_price_representation=PriceRepresentation.RAW,
            resolved_parameters=_params(period=20, denominator_excludes_current=True),
            units="ratio",
            minimum_observations=21,
        ),
        FeatureDefinition(
            feature_name="average_dollar_volume_20",
            feature_version="v0.1",
            description=(
                "Mean raw close times raw volume over the prior 20 sessions, excluding t, "
                "for liquidity filtering."
            ),
            required_price_representation=PriceRepresentation.RAW,
            resolved_parameters=_params(period=20, current_session_excluded=True),
            units="currency_volume",
            minimum_observations=21,
        ),
        FeatureDefinition(
            feature_name="atr_pct_14",
            feature_version="v0.1",
            description=(
                "Simple mean of 14 split-adjusted true ranges ending at t divided by the current "
                "split-adjusted close, expressed as percent."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=14, method="simple_true_range_mean"),
            units="percent",
            minimum_observations=15,
        ),
        FeatureDefinition(
            feature_name="distance_sma_20_pct",
            feature_version="v0.1",
            description="Current close relative to trailing SMA20, expressed as percent.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=20),
            units="percent",
            minimum_observations=20,
        ),
        FeatureDefinition(
            feature_name="distance_sma_50_pct",
            feature_version="v0.1",
            description="Current close relative to trailing SMA50, expressed as percent.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=50),
            units="percent",
            minimum_observations=50,
        ),
        FeatureDefinition(
            feature_name="distance_sma_200_pct",
            feature_version="v0.1",
            description="Current close relative to trailing SMA200, expressed as percent.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=200),
            units="percent",
            minimum_observations=200,
        ),
        FeatureDefinition(
            feature_name="sma_50_slope_20_pct",
            feature_version="v0.1",
            description="Percent change in trailing SMA50 from t-20 to t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=50, slope_intervals=20),
            units="percent",
            minimum_observations=70,
        ),
        FeatureDefinition(
            feature_name="sma_200_slope_20_pct",
            feature_version="v0.1",
            description="Percent change in trailing SMA200 from t-20 to t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=200, slope_intervals=20),
            units="percent",
            minimum_observations=220,
        ),
        FeatureDefinition(
            feature_name="sma_50_200_spread_pct",
            feature_version="v0.1",
            description="Trailing SMA50 relative to trailing SMA200 at t, expressed as percent.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(fast_period=50, slow_period=200),
            units="percent",
            minimum_observations=200,
        ),
        FeatureDefinition(
            feature_name="sma_50_200_cross_up",
            feature_version="v0.1",
            description=(
                "Numeric 1 when SMA50 is above SMA200 at t after being at or below it at t-1; "
                "otherwise 0."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(fast_period=50, slow_period=200, direction="up"),
            units="binary",
            minimum_observations=201,
        ),
        FeatureDefinition(
            feature_name="rsi_wilder_14",
            feature_version="v0.1",
            description=(
                "14-session RSI using Wilder smoothing of split-adjusted close changes, bounded "
                "from 0 to 100."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=14, smoothing="wilder"),
            units="index_0_100",
            minimum_observations=15,
        ),
        FeatureDefinition(
            feature_name="macd_line_pct",
            feature_version="v0.1",
            description=(
                "EMA12 minus EMA26 divided by current close, expressed as percent. EMA seeds use "
                "the arithmetic mean of the first complete period."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(fast_period=12, slow_period=26, ema_seed="sma"),
            units="percent",
            minimum_observations=26,
        ),
        FeatureDefinition(
            feature_name="macd_signal_pct",
            feature_version="v0.1",
            description=(
                "Nine-period EMA signal of MACD divided by current split-adjusted close, expressed "
                "as percent."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(fast_period=12, slow_period=26, signal_period=9),
            units="percent",
            minimum_observations=34,
        ),
        FeatureDefinition(
            feature_name="macd_histogram_pct",
            feature_version="v0.1",
            description="MACD line minus signal divided by current close, expressed as percent.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(fast_period=12, slow_period=26, signal_period=9),
            units="percent",
            minimum_observations=34,
        ),
        FeatureDefinition(
            feature_name="macd_bullish_cross",
            feature_version="v0.1",
            description="Numeric 1 when MACD crosses above its signal at t; otherwise 0.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(fast_period=12, slow_period=26, signal_period=9),
            units="binary",
            minimum_observations=35,
        ),
        FeatureDefinition(
            feature_name="distance_prior_high_20_pct",
            feature_version="v0.1",
            description=(
                "Current close relative to the maximum split-adjusted high of the prior 20 "
                "sessions, excluding t. Positive values indicate a close above that prior high."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=20, current_session_excluded=True),
            units="percent",
            minimum_observations=21,
        ),
        FeatureDefinition(
            feature_name="distance_prior_high_55_pct",
            feature_version="v0.1",
            description=(
                "Current close relative to the maximum split-adjusted high of the prior 55 "
                "sessions, excluding t."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=55, current_session_excluded=True),
            units="percent",
            minimum_observations=56,
        ),
        FeatureDefinition(
            feature_name="range_position_prior_20",
            feature_version="v0.1",
            description=(
                "Current close positioned within the prior 20-session high-low range, excluding t. "
                "Values may leave the 0-to-1 interval when price exits that prior range."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=20, current_session_excluded=True),
            units="ratio",
            minimum_observations=21,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class _SeriesIndicators:
    ema_12: tuple[float | None, ...]
    ema_26: tuple[float | None, ...]
    macd: tuple[float | None, ...]
    macd_signal_9: tuple[float | None, ...]
    rsi_wilder_14: tuple[float | None, ...]


def compute_market_analysis_feature_frame(
    bars: Iterable[DailyBar],
    *,
    feature_set: FeatureSetDefinition = MARKET_ANALYSIS_FEATURE_SET,
) -> tuple[FeatureValue, ...]:
    """Compute the market-analysis pack using only information available at each session t."""

    materialized = tuple(
        sorted(bars, key=lambda item: (str(item.instrument_id), item.trade_date, item.provider_id))
    )
    if not materialized:
        raise MarketAnalysisFeatureInputError(
            "market analysis features require canonical daily bars"
        )
    versions = {item.dataset_version for item in materialized}
    if len(versions) != 1:
        raise MarketAnalysisFeatureInputError(
            "market analysis features cannot mix dataset versions"
        )
    if any(item.quality_status is not QualityStatus.PASS for item in materialized):
        raise MarketAnalysisFeatureInputError(
            "market analysis features require PASS canonical input"
        )

    by_instrument: dict[str, list[DailyBar]] = {}
    seen: set[tuple[str, date]] = set()
    for item in materialized:
        key = (str(item.instrument_id), item.trade_date)
        if key in seen:
            raise MarketAnalysisFeatureInputError(
                f"duplicate canonical instrument/date in market analysis input: {key}"
            )
        seen.add(key)
        by_instrument.setdefault(str(item.instrument_id), []).append(item)

    values: list[FeatureValue] = []
    for instrument_bars in by_instrument.values():
        ordered = tuple(sorted(instrument_bars, key=lambda item: item.trade_date))
        indicators = _build_series_indicators(ordered)
        for index, bar in enumerate(ordered):
            for definition in feature_set.definitions:
                status, feature_value = _calculate(definition, ordered, index, indicators)
                values.append(
                    FeatureValue(
                        instrument_id=bar.instrument_id,
                        trade_date=bar.trade_date,
                        feature_name=definition.feature_name,
                        feature_version=definition.feature_version,
                        resolved_parameters=definition.resolved_parameters,
                        value=feature_value,
                        units=definition.units,
                        availability_status=status,
                        dataset_version=bar.dataset_version,
                        feature_set_version=feature_set.feature_set_version,
                    )
                )
    return tuple(
        sorted(
            values,
            key=lambda item: (
                str(item.instrument_id),
                item.trade_date,
                item.feature_name,
                item.feature_version,
            ),
        )
    )


def compute_incremental_market_analysis_feature_frame(
    history_bars: Iterable[DailyBar],
    new_bars: Iterable[DailyBar],
    *,
    feature_set: FeatureSetDefinition = MARKET_ANALYSIS_FEATURE_SET,
) -> tuple[FeatureValue, ...]:
    """Return new-session feature values with batch-equivalent point-in-time semantics."""

    history = tuple(history_bars)
    new = tuple(new_bars)
    if not new:
        return ()
    latest: dict[str, date] = {}
    for bar in history:
        key = str(bar.instrument_id)
        latest[key] = max(latest.get(key, bar.trade_date), bar.trade_date)
    new_keys: set[tuple[str, date]] = set()
    for bar in new:
        key = str(bar.instrument_id)
        if key in latest and bar.trade_date <= latest[key]:
            raise MarketAnalysisFeatureInputError(
                f"incremental market-analysis rows must follow history for {key}"
            )
        row_key = (key, bar.trade_date)
        if row_key in new_keys:
            raise MarketAnalysisFeatureInputError(
                f"duplicate incremental instrument/date: {row_key}"
            )
        new_keys.add(row_key)
    all_values = compute_market_analysis_feature_frame((*history, *new), feature_set=feature_set)
    return tuple(
        item for item in all_values if (str(item.instrument_id), item.trade_date) in new_keys
    )


def _calculate(
    definition: FeatureDefinition,
    bars: Sequence[DailyBar],
    index: int,
    indicators: _SeriesIndicators,
) -> tuple[FeatureAvailabilityStatus, float | None]:
    if index + 1 < definition.minimum_observations:
        return FeatureAvailabilityStatus.WARMUP, None

    if definition.feature_name in {"return_5", "return_20", "return_252"}:
        intervals = _integer_parameter(definition, "intervals")
        current = _split_close(bars[index])
        prior_close = _split_close(bars[index - intervals])
        if current is None or prior_close is None or prior_close <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, current / prior_close - 1.0

    if definition.feature_name == "realized_volatility_20":
        intervals = _integer_parameter(definition, "return_intervals")
        closes = [_split_close(item) for item in bars[index - intervals : index + 1]]
        if any(candidate is None or candidate <= 0 for candidate in closes):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        numeric = _require_values(closes)
        log_returns = [math.log(numeric[pos] / numeric[pos - 1]) for pos in range(1, len(numeric))]
        value = stdev(log_returns) * math.sqrt(252.0)
        return FeatureAvailabilityStatus.AVAILABLE, value

    if definition.feature_name == "relative_volume_20":
        period = _integer_parameter(definition, "period")
        current_volume = bars[index].volume_raw
        prior_volumes = [item.volume_raw for item in bars[index - period : index]]
        if (
            not math.isfinite(current_volume)
            or current_volume < 0
            or any(not math.isfinite(candidate) or candidate < 0 for candidate in prior_volumes)
        ):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        denominator = math.fsum(prior_volumes) / period
        if denominator <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, current_volume / denominator

    if definition.feature_name == "average_dollar_volume_20":
        period = _integer_parameter(definition, "period")
        dollar_volumes: list[float] = []
        for item in bars[index - period : index]:
            close = _finite_optional(item.close_raw)
            volume = item.volume_raw
            if close is None or close <= 0 or not math.isfinite(volume) or volume < 0:
                return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
            dollar_volumes.append(close * volume)
        return FeatureAvailabilityStatus.AVAILABLE, math.fsum(dollar_volumes) / period

    if definition.feature_name == "atr_pct_14":
        period = _integer_parameter(definition, "period")
        current_close = _split_close(bars[index])
        if current_close is None or current_close <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        true_ranges: list[float] = []
        for current_index in range(index - period + 1, index + 1):
            current_high = _split_high(bars[current_index])
            current_low = _split_low(bars[current_index])
            previous_close = _split_close(bars[current_index - 1])
            if current_high is None or current_low is None or previous_close is None:
                return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
            true_ranges.append(
                max(
                    current_high - current_low,
                    abs(current_high - previous_close),
                    abs(current_low - previous_close),
                )
            )
        atr = math.fsum(true_ranges) / period
        return FeatureAvailabilityStatus.AVAILABLE, atr / current_close * 100.0

    if definition.feature_name in {
        "distance_sma_20_pct",
        "distance_sma_50_pct",
        "distance_sma_200_pct",
    }:
        period = _integer_parameter(definition, "period")
        sma = _sma_at(bars, index, period)
        current = _split_close(bars[index])
        if current is None or current <= 0 or sma is None or sma <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, (current / sma - 1.0) * 100.0

    if definition.feature_name in {"sma_50_slope_20_pct", "sma_200_slope_20_pct"}:
        period = _integer_parameter(definition, "period")
        slope_intervals = _integer_parameter(definition, "slope_intervals")
        current_sma = _sma_at(bars, index, period)
        prior_sma = _sma_at(bars, index - slope_intervals, period)
        if current_sma is None or prior_sma is None or prior_sma <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, (current_sma / prior_sma - 1.0) * 100.0

    if definition.feature_name in {"sma_50_200_spread_pct", "sma_50_200_cross_up"}:
        fast_period = _integer_parameter(definition, "fast_period")
        slow_period = _integer_parameter(definition, "slow_period")
        fast = _sma_at(bars, index, fast_period)
        slow = _sma_at(bars, index, slow_period)
        if fast is None or slow is None or slow <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        if definition.feature_name == "sma_50_200_spread_pct":
            return FeatureAvailabilityStatus.AVAILABLE, (fast / slow - 1.0) * 100.0
        prior_fast = _sma_at(bars, index - 1, fast_period)
        prior_slow = _sma_at(bars, index - 1, slow_period)
        if prior_fast is None or prior_slow is None:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        crossed = fast > slow and prior_fast <= prior_slow
        return FeatureAvailabilityStatus.AVAILABLE, 1.0 if crossed else 0.0

    if definition.feature_name == "rsi_wilder_14":
        rsi_value = indicators.rsi_wilder_14[index]
        return _indicator_value(rsi_value)

    if definition.feature_name in {
        "macd_line_pct",
        "macd_signal_pct",
        "macd_histogram_pct",
        "macd_bullish_cross",
    }:
        current_close = _split_close(bars[index])
        if current_close is None or current_close <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        macd = indicators.macd[index]
        signal = indicators.macd_signal_9[index]
        if definition.feature_name == "macd_line_pct":
            return _indicator_value(None if macd is None else macd / current_close * 100.0)
        if signal is None or macd is None:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        if definition.feature_name == "macd_signal_pct":
            return FeatureAvailabilityStatus.AVAILABLE, signal / current_close * 100.0
        histogram = macd - signal
        if definition.feature_name == "macd_histogram_pct":
            return FeatureAvailabilityStatus.AVAILABLE, histogram / current_close * 100.0
        prior_macd = indicators.macd[index - 1]
        prior_signal = indicators.macd_signal_9[index - 1]
        if prior_macd is None or prior_signal is None:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        crossed = macd > signal and prior_macd <= prior_signal
        return FeatureAvailabilityStatus.AVAILABLE, 1.0 if crossed else 0.0

    if definition.feature_name in {
        "distance_prior_high_20_pct",
        "distance_prior_high_55_pct",
        "range_position_prior_20",
    }:
        period = _integer_parameter(definition, "period")
        prior_bars = bars[index - period : index]
        highs = [_split_high(item) for item in prior_bars]
        current = _split_close(bars[index])
        if current is None or current <= 0 or any(candidate is None for candidate in highs):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        numeric_highs = _require_values(highs)
        prior_high = max(numeric_highs)
        if definition.feature_name.startswith("distance_prior_high_"):
            if prior_high <= 0:
                return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
            return FeatureAvailabilityStatus.AVAILABLE, (current / prior_high - 1.0) * 100.0
        lows = [_split_low(item) for item in prior_bars]
        if any(candidate is None for candidate in lows):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        prior_low = min(_require_values(lows))
        width = prior_high - prior_low
        if width <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, (current - prior_low) / width

    raise MarketAnalysisFeatureInputError(
        f"unimplemented market analysis feature: {definition.feature_name}"
    )


def _build_series_indicators(bars: Sequence[DailyBar]) -> _SeriesIndicators:
    closes = tuple(_split_close(item) for item in bars)
    ema_12 = _ema_series(closes, 12)
    ema_26 = _ema_series(closes, 26)
    macd = tuple(
        fast - slow if fast is not None and slow is not None else None
        for fast, slow in zip(ema_12, ema_26, strict=True)
    )
    signal = _ema_series(macd, 9)
    rsi = _wilder_rsi_series(closes, 14)
    return _SeriesIndicators(
        ema_12=ema_12,
        ema_26=ema_26,
        macd=macd,
        macd_signal_9=signal,
        rsi_wilder_14=rsi,
    )


def _ema_series(values: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    if period < 1:
        raise ValueError("EMA period must be positive")
    result: list[float | None] = [None] * len(values)
    alpha = 2.0 / (period + 1.0)
    seed: list[float] = []
    previous: float | None = None
    for index, value in enumerate(values):
        if value is None or not math.isfinite(value):
            seed.clear()
            previous = None
            continue
        if previous is None:
            seed.append(value)
            if len(seed) > period:
                seed.pop(0)
            if len(seed) == period:
                previous = math.fsum(seed) / period
                result[index] = previous
            continue
        previous = alpha * value + (1.0 - alpha) * previous
        result[index] = previous
    return tuple(result)


def _wilder_rsi_series(closes: Sequence[float | None], period: int) -> tuple[float | None, ...]:
    if period < 1:
        raise ValueError("RSI period must be positive")
    result: list[float | None] = [None] * len(closes)
    gains: list[float] = []
    losses: list[float] = []
    average_gain: float | None = None
    average_loss: float | None = None
    previous_close: float | None = None
    for index, close in enumerate(closes):
        if close is None or not math.isfinite(close) or close <= 0:
            gains.clear()
            losses.clear()
            average_gain = None
            average_loss = None
            previous_close = None
            continue
        if previous_close is None:
            previous_close = close
            continue
        change = close - previous_close
        previous_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        if average_gain is None or average_loss is None:
            gains.append(gain)
            losses.append(loss)
            if len(gains) > period:
                gains.pop(0)
                losses.pop(0)
            if len(gains) < period:
                continue
            average_gain = math.fsum(gains) / period
            average_loss = math.fsum(losses) / period
        else:
            average_gain = (average_gain * (period - 1) + gain) / period
            average_loss = (average_loss * (period - 1) + loss) / period
        result[index] = _rsi_from_averages(average_gain, average_loss)
    return tuple(result)


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _sma_at(bars: Sequence[DailyBar], index: int, period: int) -> float | None:
    start = index - period + 1
    if index < 0 or start < 0:
        return None
    closes = [_split_close(item) for item in bars[start : index + 1]]
    if any(candidate is None for candidate in closes):
        return None
    numeric = _require_values(closes)
    return math.fsum(numeric) / period


def _indicator_value(
    value: float | None,
) -> tuple[FeatureAvailabilityStatus, float | None]:
    if value is None or not math.isfinite(value):
        return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
    return FeatureAvailabilityStatus.AVAILABLE, value


def _integer_parameter(definition: FeatureDefinition, name: str) -> int:
    value = definition.resolved_parameters.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MarketAnalysisFeatureInputError(
            f"{definition.feature_name} has invalid integer parameter {name}"
        )
    return value


def _split_close(bar: DailyBar) -> float | None:
    return _finite_optional(bar.close_split_adjusted)


def _split_high(bar: DailyBar) -> float | None:
    return _finite_optional(bar.high_split_adjusted)


def _split_low(bar: DailyBar) -> float | None:
    return _finite_optional(bar.low_split_adjusted)


def _finite_optional(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


def _require_values(values: Sequence[float | None]) -> tuple[float, ...]:
    if any(candidate is None for candidate in values):
        raise AssertionError("optional values must be checked before conversion")
    return tuple(float(value) for value in values if value is not None)


__all__ = [
    "MARKET_ANALYSIS_FEATURE_SET",
    "MARKET_ANALYSIS_FEATURE_SET_VERSION",
    "MarketAnalysisFeatureInputError",
    "compute_incremental_market_analysis_feature_frame",
    "compute_market_analysis_feature_frame",
]
