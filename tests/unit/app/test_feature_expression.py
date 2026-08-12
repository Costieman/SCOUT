from __future__ import annotations

import pytest

from trade_scout.app.feature_expression import FeatureExpressionError, compile_feature_expression


_ALLOWED = frozenset(
    {
        "return_20",
        "return_252",
        "relative_volume_20",
        "atr_pct_14",
        "distance_sma_200_pct",
    }
)


def test_feature_expression_supports_boolean_arithmetic_and_comparisons() -> None:
    expression = compile_feature_expression(
        "return_20 >= 0.05 and relative_volume_20 >= 1.5 and atr_pct_14 < 4",
        allowed_names=_ALLOWED,
    )

    assert expression.evaluate(
        {
            "return_20": 0.08,
            "relative_volume_20": 2.0,
            "atr_pct_14": 3.2,
        }
    )
    assert not expression.evaluate(
        {
            "return_20": 0.02,
            "relative_volume_20": 2.0,
            "atr_pct_14": 3.2,
        }
    )


def test_feature_expression_can_compare_derived_numeric_terms() -> None:
    expression = compile_feature_expression(
        "return_20 / atr_pct_14 > 0.015 or distance_sma_200_pct > 20",
        allowed_names=_ALLOWED,
    )

    assert expression.evaluate({"return_20": 0.08, "atr_pct_14": 4.0, "distance_sma_200_pct": 5.0})
    assert not expression.evaluate(
        {"return_20": 0.02, "atr_pct_14": 4.0, "distance_sma_200_pct": 5.0}
    )


def test_unavailable_feature_fails_closed() -> None:
    expression = compile_feature_expression(
        "return_252 > 0 and relative_volume_20 > 1",
        allowed_names=_ALLOWED,
    )

    assert expression.evaluate({"return_252": None, "relative_volume_20": 2.0}) is False
    assert expression.evaluate({"relative_volume_20": 2.0}) is False


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('echo unsafe')",
        "return_20.__class__",
        "[return_20][0]",
        "lambda: return_20",
        "unknown_feature > 0",
        "'text' == 'text'",
    ],
)
def test_unsafe_or_unknown_constructs_are_rejected(source: str) -> None:
    with pytest.raises(FeatureExpressionError):
        compile_feature_expression(source, allowed_names=_ALLOWED)


def test_expression_requires_boolean_result() -> None:
    expression = compile_feature_expression("return_20 + 1", allowed_names=_ALLOWED)

    with pytest.raises(FeatureExpressionError, match="boolean"):
        expression.evaluate({"return_20": 0.1})


def test_division_by_zero_is_explicit_error() -> None:
    expression = compile_feature_expression(
        "return_20 / atr_pct_14 > 1",
        allowed_names=_ALLOWED,
    )

    with pytest.raises(FeatureExpressionError, match="arithmetic failed"):
        expression.evaluate({"return_20": 0.1, "atr_pct_14": 0.0})
