"""Resolve deterministic parameterized-indicator feature names embedded in strategy expressions."""

from __future__ import annotations

import ast
import re

from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    MovingAverageType,
    ParameterizedIndicatorSpec,
    PriceSource,
)

_PREFIX = "pi__"
_MACD_SUFFIX = re.compile(r"^f(?P<fast>\d+)s(?P<slow>\d+)g(?P<signal>\d+)$")


def parse_parameterized_feature_name(feature_name: str) -> ParameterizedIndicatorSpec:
    """Decode one generated feature identifier back to its fully resolved indicator spec."""

    parts = feature_name.split("__")
    if len(parts) != 6 or parts[0] != "pi":
        raise ValueError(f"not a parameterized indicator feature name: {feature_name!r}")
    family = IndicatorFamily(parts[1])
    metric = IndicatorMetric(parts[2])
    source = PriceSource(parts[3])
    period_token = parts[4]
    if not period_token.startswith("p") or not period_token[1:].isdigit():
        raise ValueError(f"invalid parameterized indicator period: {period_token!r}")
    period = int(period_token[1:])
    suffix = parts[5]

    if family is IndicatorFamily.MOVING_AVERAGE:
        return ParameterizedIndicatorSpec(
            family=family,
            metric=metric,
            period=period,
            source=source,
            moving_average_type=MovingAverageType(suffix),
        )
    if family is IndicatorFamily.BOLLINGER_BANDS:
        if not suffix.startswith("k"):
            raise ValueError(f"invalid Bollinger deviation token: {suffix!r}")
        return ParameterizedIndicatorSpec(
            family=family,
            metric=metric,
            period=period,
            source=source,
            standard_deviations=_decode_number(suffix[1:]),
        )
    if family is IndicatorFamily.MACD:
        match = _MACD_SUFFIX.match(suffix)
        if match is None:
            raise ValueError(f"invalid MACD parameter token: {suffix!r}")
        return ParameterizedIndicatorSpec(
            family=family,
            metric=metric,
            period=period,
            source=source,
            fast_period=int(match.group("fast")),
            slow_period=int(match.group("slow")),
            signal_period=int(match.group("signal")),
        )
    return ParameterizedIndicatorSpec(
        family=family,
        metric=metric,
        period=period,
        source=source,
    )


def extract_parameterized_specs(expression: str) -> tuple[ParameterizedIndicatorSpec, ...]:
    """Return every unique parameterized feature referenced by one safe strategy expression."""

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError("cannot inspect malformed strategy expression") from exc
    names = sorted(
        {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id.startswith(_PREFIX)
        }
    )
    return tuple(parse_parameterized_feature_name(name) for name in names)


def _decode_number(token: str) -> float:
    try:
        return float(token.replace("m", "-").replace("p", "."))
    except ValueError as exc:
        raise ValueError(f"invalid parameterized numeric token {token!r}") from exc


__all__ = ["extract_parameterized_specs", "parse_parameterized_feature_name"]
