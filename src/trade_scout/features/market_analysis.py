"""Reusable point-in-time market-analysis features for strategy research and charting."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
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

MARKET_ANALYSIS_FEATURE_SET_VERSION = "market-analysis-features-v0.1"


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
            description=(
                "Split-adjusted close return over five trading-session intervals ending at t."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(intervals=5),
            units="decimal_return",
            minimum_observations=6,
        ),
        FeatureDefinition(
            feature_name="return_20",
            feature_version="v0.1",
            description=(
                "Split-adjusted close return over 20 trading-session intervals ending at t."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(intervals=20),
            units="decimal_return",
            minimum_observations=21,
        ),
        FeatureDefinition(
            feature_name="return_252",
            feature_version="v0.1",
            description=(
                "Split-adjusted close return over 252 trading-session intervals ending at t."
            ),
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
                "Current raw reported volume divided by the arithmetic mean of the prior 20 "
                "sessions, excluding t from the denominator."
            ),
            required_price_representation=PriceRepresentation.RAW,
            resolved_parameters=_params(period=20, denominator_excludes_current=True),
            units="ratio",
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
            feature_name="distance_sma_50_pct",
            feature_version="v0.1",
            description=(
                "Current split-adjusted close relative to trailing SMA50, expressed as percent."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=50),
            units="percent",
            minimum_observations=50,
        ),
        FeatureDefinition(
            feature_name="distance_sma_200_pct",
            feature_version="v0.1",
            description=(
                "Current split-adjusted close relative to trailing SMA200, expressed as percent."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=200),
            units="percent",
            minimum_observations=200,
        ),
    ),
)


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
        for index, bar in enumerate(ordered):
            for definition in feature_set.definitions:
                status, value = _calculate(definition, ordered, index)
                values.append(
                    FeatureValue(
                        instrument_id=bar.instrument_id,
                        trade_date=bar.trade_date,
                        feature_name=definition.feature_name,
                        feature_version=definition.feature_version,
                        resolved_parameters=definition.resolved_parameters,
                        value=value,
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
) -> tuple[FeatureAvailabilityStatus, float | None]:
    if index + 1 < definition.minimum_observations:
        return FeatureAvailabilityStatus.WARMUP, None

    if definition.feature_name in {"return_5", "return_20", "return_252"}:
        intervals = _integer_parameter(definition, "intervals")
        current = _split_close(bars[index])
        prior = _split_close(bars[index - intervals])
        if current is None or prior is None or prior <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, current / prior - 1.0

    if definition.feature_name == "realized_volatility_20":
        intervals = _integer_parameter(definition, "return_intervals")
        closes = [_split_close(item) for item in bars[index - intervals : index + 1]]
        if any(value is None or value <= 0 for value in closes):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        numeric = _require_values(closes)
        log_returns = [math.log(numeric[pos] / numeric[pos - 1]) for pos in range(1, len(numeric))]
        value = stdev(log_returns) * math.sqrt(252.0)
        return FeatureAvailabilityStatus.AVAILABLE, value

    if definition.feature_name == "relative_volume_20":
        period = _integer_parameter(definition, "period")
        current = bars[index].volume_raw
        prior = [item.volume_raw for item in bars[index - period : index]]
        if (
            not math.isfinite(current)
            or current < 0
            or any(not math.isfinite(value) or value < 0 for value in prior)
        ):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        denominator = math.fsum(prior) / period
        if denominator <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, current / denominator

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

    if definition.feature_name in {"distance_sma_50_pct", "distance_sma_200_pct"}:
        period = _integer_parameter(definition, "period")
        closes = [_split_close(item) for item in bars[index - period + 1 : index + 1]]
        current = _split_close(bars[index])
        if current is None or current <= 0 or any(value is None for value in closes):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        numeric = _require_values(closes)
        sma = math.fsum(numeric) / period
        if sma <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, (current / sma - 1.0) * 100.0

    raise MarketAnalysisFeatureInputError(
        f"unimplemented market analysis feature: {definition.feature_name}"
    )


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
    if any(value is None for value in values):
        raise AssertionError("optional values must be checked before conversion")
    return tuple(float(value) for value in values if value is not None)


__all__ = [
    "MARKET_ANALYSIS_FEATURE_SET",
    "MARKET_ANALYSIS_FEATURE_SET_VERSION",
    "MarketAnalysisFeatureInputError",
    "compute_incremental_market_analysis_feature_frame",
    "compute_market_analysis_feature_frame",
]
