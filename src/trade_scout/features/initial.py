"""Initial provider-independent feature set for the Phase 2 foundation slice."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from types import MappingProxyType

from trade_scout.data.contracts import DailyBar, PriceRepresentation, QualityStatus
from trade_scout.features.contracts import (
    FeatureAvailabilityStatus,
    FeatureDefinition,
    FeatureSetDefinition,
    FeatureValue,
)

INITIAL_FEATURE_SET_VERSION = "phase2-initial-features-v0.1"


class FeatureInputError(ValueError):
    """Raised when canonical inputs cannot safely support deterministic feature calculation."""


def _params(**values: str | int | float | bool) -> Mapping[str, str | int | float | bool]:
    return MappingProxyType(values)


INITIAL_FEATURE_SET = FeatureSetDefinition(
    feature_set_version=INITIAL_FEATURE_SET_VERSION,
    definitions=(
        FeatureDefinition(
            feature_name="sma_50",
            feature_version="v0.1",
            description="Arithmetic mean of the trailing 50 split-adjusted closes, including t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=50),
            units="price",
            minimum_observations=50,
        ),
        FeatureDefinition(
            feature_name="sma_200",
            feature_version="v0.1",
            description="Arithmetic mean of the trailing 200 split-adjusted closes, including t.",
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=200),
            units="price",
            minimum_observations=200,
        ),
        FeatureDefinition(
            feature_name="return_60",
            feature_version="v0.1",
            description=(
                "Split-adjusted close return from 60 trading-session intervals earlier to t."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(intervals=60),
            units="decimal_return",
            minimum_observations=61,
        ),
        FeatureDefinition(
            feature_name="avg_dollar_volume_20",
            feature_version="v0.1",
            description=(
                "Arithmetic mean of raw close multiplied by raw reported volume over 20 sessions."
            ),
            required_price_representation=PriceRepresentation.RAW,
            resolved_parameters=_params(period=20),
            units="currency_notional",
            minimum_observations=20,
        ),
        FeatureDefinition(
            feature_name="rolling_range_pct_30",
            feature_version="v0.1",
            description=(
                "Trailing 30-session split-adjusted high-low span divided by current "
                "split-adjusted close, expressed as percent."
            ),
            required_price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            resolved_parameters=_params(period=30, reference="current_close"),
            units="percent",
            minimum_observations=30,
        ),
    ),
)


def initial_feature_definition_sha256(
    feature_set: FeatureSetDefinition = INITIAL_FEATURE_SET,
) -> str:
    """Return a deterministic checksum of the registered mathematical feature definitions."""

    payload = {
        "feature_set_version": feature_set.feature_set_version,
        "definitions": [
            {
                "feature_name": item.feature_name,
                "feature_version": item.feature_version,
                "description": item.description,
                "required_price_representation": item.required_price_representation.value,
                "resolved_parameters": dict(sorted(item.resolved_parameters.items())),
                "units": item.units,
                "minimum_observations": item.minimum_observations,
            }
            for item in feature_set.definitions
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_initial_feature_frame(
    bars: Iterable[DailyBar],
    *,
    feature_set: FeatureSetDefinition = INITIAL_FEATURE_SET,
) -> tuple[FeatureValue, ...]:
    """Compute trailing point-in-time features without repair, shortening, or future data."""

    materialized = tuple(
        sorted(bars, key=lambda item: (str(item.instrument_id), item.trade_date, item.provider_id))
    )
    if not materialized:
        raise FeatureInputError("feature calculation requires at least one canonical daily bar")
    dataset_versions = {item.dataset_version for item in materialized}
    if len(dataset_versions) != 1:
        raise FeatureInputError("feature calculation cannot mix canonical dataset versions")
    for item in materialized:
        if item.quality_status is not QualityStatus.PASS:
            raise FeatureInputError(
                f"feature foundation requires PASS input; {item.instrument_id} "
                f"{item.trade_date} is {item.quality_status}"
            )

    by_instrument: dict[str, list[DailyBar]] = {}
    seen: set[tuple[str, date]] = set()
    for item in materialized:
        key = (str(item.instrument_id), item.trade_date)
        if key in seen:
            raise FeatureInputError(f"duplicate canonical instrument/date in feature input: {key}")
        seen.add(key)
        by_instrument.setdefault(str(item.instrument_id), []).append(item)

    values: list[FeatureValue] = []
    for instrument_bars in by_instrument.values():
        ordered = tuple(sorted(instrument_bars, key=lambda item: item.trade_date))
        for index, bar in enumerate(ordered):
            for definition in feature_set.definitions:
                status, value = _calculate_feature(definition, ordered, index)
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


def compute_incremental_initial_feature_frame(
    history_bars: Iterable[DailyBar],
    new_bars: Iterable[DailyBar],
    *,
    feature_set: FeatureSetDefinition = INITIAL_FEATURE_SET,
) -> tuple[FeatureValue, ...]:
    """Compute new-session features with full trailing state and batch-equivalent semantics.

    This first implementation deliberately favors correctness over optimization: it recomputes the bounded
    history plus new rows, then returns only feature observations for the new canonical keys. Later cache or
    columnar optimizations must reproduce this result exactly within declared tolerance.
    """

    history = tuple(history_bars)
    new = tuple(new_bars)
    if not new:
        return ()

    history_latest: dict[str, date] = {}
    for bar in history:
        key = str(bar.instrument_id)
        latest = history_latest.get(key)
        if latest is None or bar.trade_date > latest:
            history_latest[key] = bar.trade_date
    new_keys: set[tuple[str, date]] = set()
    for bar in new:
        instrument = str(bar.instrument_id)
        latest = history_latest.get(instrument)
        if latest is not None and bar.trade_date <= latest:
            raise FeatureInputError(
                "incremental feature rows must be strictly later than supplied history "
                f"for {instrument}"
            )
        key = (instrument, bar.trade_date)
        if key in new_keys:
            raise FeatureInputError(f"duplicate incremental instrument/date: {key}")
        new_keys.add(key)

    all_values = compute_initial_feature_frame((*history, *new), feature_set=feature_set)
    return tuple(
        item for item in all_values if (str(item.instrument_id), item.trade_date) in new_keys
    )


def _calculate_feature(
    definition: FeatureDefinition,
    bars: Sequence[DailyBar],
    index: int,
) -> tuple[FeatureAvailabilityStatus, float | None]:
    if index + 1 < definition.minimum_observations:
        return FeatureAvailabilityStatus.WARMUP, None

    if definition.feature_name in {"sma_50", "sma_200"}:
        period = _integer_parameter(definition, "period")
        closes = [_split_close(item) for item in bars[index - period + 1 : index + 1]]
        if any(value is None for value in closes):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        numeric = _require_optional_values(closes)
        return FeatureAvailabilityStatus.AVAILABLE, math.fsum(numeric) / period

    if definition.feature_name == "return_60":
        intervals = _integer_parameter(definition, "intervals")
        current = _split_close(bars[index])
        prior = _split_close(bars[index - intervals])
        if current is None or prior is None or prior <= 0:
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, current / prior - 1.0

    if definition.feature_name == "avg_dollar_volume_20":
        period = _integer_parameter(definition, "period")
        window = bars[index - period + 1 : index + 1]
        notionals = [item.close_raw * item.volume_raw for item in window]
        if not all(math.isfinite(value) and value >= 0 for value in notionals):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        return FeatureAvailabilityStatus.AVAILABLE, math.fsum(notionals) / period

    if definition.feature_name == "rolling_range_pct_30":
        period = _integer_parameter(definition, "period")
        window = bars[index - period + 1 : index + 1]
        highs = [_split_high(item) for item in window]
        lows = [_split_low(item) for item in window]
        current_close = _split_close(bars[index])
        if (
            current_close is None
            or current_close <= 0
            or any(value is None for value in highs)
            or any(value is None for value in lows)
        ):
            return FeatureAvailabilityStatus.INPUT_UNAVAILABLE, None
        numeric_highs = _require_optional_values(highs)
        numeric_lows = _require_optional_values(lows)
        value = (max(numeric_highs) - min(numeric_lows)) / current_close * 100.0
        return FeatureAvailabilityStatus.AVAILABLE, value

    raise FeatureInputError(f"unimplemented registered feature: {definition.feature_name}")


def _integer_parameter(definition: FeatureDefinition, name: str) -> int:
    value = definition.resolved_parameters.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise FeatureInputError(f"{definition.feature_name} has invalid integer parameter {name}")
    return value


def _split_close(bar: DailyBar) -> float | None:
    return _finite_optional(bar.close_split_adjusted)


def _split_high(bar: DailyBar) -> float | None:
    return _finite_optional(bar.high_split_adjusted)


def _split_low(bar: DailyBar) -> float | None:
    return _finite_optional(bar.low_split_adjusted)


def _finite_optional(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


def _require_optional_values(values: Sequence[float | None]) -> tuple[float, ...]:
    if any(value is None for value in values):
        raise AssertionError("optional values must be checked before conversion")
    return tuple(float(value) for value in values if value is not None)


__all__ = [
    "FeatureInputError",
    "INITIAL_FEATURE_SET",
    "INITIAL_FEATURE_SET_VERSION",
    "compute_incremental_initial_feature_frame",
    "compute_initial_feature_frame",
    "initial_feature_definition_sha256",
]
