"""Typed visual-rule configuration compiled into the existing safe feature-expression engine.

The browser composer submits structured conditions instead of asking operators to type Python-like
expressions. The application compiles those conditions to the same restricted feature-expression
language already used by exploratory strategy research, so the visual layer does not create a
second backtest implementation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from trade_scout.statistics.strategy_research import available_strategy_features


class RuleJoin(StrEnum):
    """How a condition is combined with the condition before it."""

    AND = "and"
    OR = "or"


class RuleOperator(StrEnum):
    """Comparison operators exposed by the visual composer."""

    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="


@dataclass(frozen=True, slots=True)
class VisualCondition:
    """One point-in-time feature comparison selected in the visual rule builder."""

    feature_name: str
    operator: RuleOperator
    value: float
    join: RuleJoin = RuleJoin.AND

    def __post_init__(self) -> None:
        if self.feature_name not in available_strategy_features():
            raise ValueError(f"unknown visual-rule feature {self.feature_name!r}")
        if not math.isfinite(self.value):
            raise ValueError("visual-rule comparison value must be finite")

    @property
    def expression_fragment(self) -> str:
        """Return the deterministic safe-expression fragment for this condition."""

        return f"{self.feature_name} {self.operator.value} {_format_number(self.value)}"


@dataclass(frozen=True, slots=True)
class VisualRuleSet:
    """Ordered visual conditions with explicit left-to-right AND/OR composition."""

    conditions: tuple[VisualCondition, ...]
    version: str = "visual-rule-set-v0.1"

    def __post_init__(self) -> None:
        if not self.conditions:
            raise ValueError("visual rule set requires at least one condition")
        if len(self.conditions) > 50:
            raise ValueError("visual rule set supports at most 50 conditions")

    @property
    def expression(self) -> str:
        """Compile to an explicitly parenthesized feature expression.

        Composition is intentionally left-to-right. Explicit parentheses remove ambiguity between
        AND and OR and make the frozen research definition reproduce exactly what the operator built.
        """

        resolved = self.conditions[0].expression_fragment
        for condition in self.conditions[1:]:
            resolved = f"({resolved} {condition.join.value} {condition.expression_fragment})"
        return resolved


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".12g")


__all__ = ["RuleJoin", "RuleOperator", "VisualCondition", "VisualRuleSet"]
