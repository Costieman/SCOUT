"""Typed visual-rule configuration compiled into the existing safe feature-expression engine.

The browser composer submits structured conditions instead of asking operators to type Python-like
expressions. The application compiles those conditions to the same restricted feature-expression
language already used by exploratory strategy research, so the visual layer does not create a
second backtest implementation.
"""

from __future__ import annotations

import ast
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


def recover_visual_conditions(source: str) -> tuple[VisualCondition, ...]:
    """Recover simple visual rows from a compatible expression, otherwise return an empty tuple.

    This is presentation recovery only. The executed research definition remains the original safe
    expression. Recovery accepts comparison leaves joined by AND/OR and rejects arithmetic or other
    constructs rather than guessing how they should appear in the visual UI.
    """

    try:
        tree = ast.parse(source.strip(), mode="eval")
        recovered = _recover_node(tree.body)
    except (SyntaxError, TypeError, ValueError):
        return ()
    return tuple(recovered) if recovered else ()


def _recover_node(node: ast.AST) -> list[VisualCondition] | None:
    leaf = _recover_comparison(node)
    if leaf is not None:
        return [leaf]
    if not isinstance(node, ast.BoolOp) or not isinstance(node.op, (ast.And, ast.Or)):
        return None
    join = RuleJoin.AND if isinstance(node.op, ast.And) else RuleJoin.OR
    result: list[VisualCondition] = []
    for index, child in enumerate(node.values):
        child_conditions = _recover_node(child)
        if not child_conditions:
            return None
        if index > 0:
            first = child_conditions[0]
            child_conditions[0] = VisualCondition(
                feature_name=first.feature_name,
                operator=first.operator,
                value=first.value,
                join=join,
            )
        result.extend(child_conditions)
    return result


def _recover_comparison(node: ast.AST) -> VisualCondition | None:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
        return None
    if not isinstance(node.left, ast.Name):
        return None
    value = _numeric_constant(node.comparators[0])
    if value is None:
        return None
    operator = _operator_from_ast(node.ops[0])
    if operator is None:
        return None
    try:
        return VisualCondition(node.left.id, operator, value)
    except ValueError:
        return None


def _numeric_constant(node: ast.AST) -> float | None:
    if (
        isinstance(node, ast.Constant)
        and not isinstance(node.value, bool)
        and isinstance(node.value, (int, float))
    ):
        value = float(node.value)
        return value if math.isfinite(value) else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _numeric_constant(node.operand)
        if value is None:
            return None
        return -value if isinstance(node.op, ast.USub) else value
    return None


def _operator_from_ast(node: ast.cmpop) -> RuleOperator | None:
    mapping: tuple[tuple[type[ast.cmpop], RuleOperator], ...] = (
        (ast.Gt, RuleOperator.GREATER_THAN),
        (ast.GtE, RuleOperator.GREATER_THAN_OR_EQUAL),
        (ast.Lt, RuleOperator.LESS_THAN),
        (ast.LtE, RuleOperator.LESS_THAN_OR_EQUAL),
        (ast.Eq, RuleOperator.EQUAL),
        (ast.NotEq, RuleOperator.NOT_EQUAL),
    )
    for node_type, resolved in mapping:
        if isinstance(node, node_type):
            return resolved
    return None


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".12g")


__all__ = [
    "RuleJoin",
    "RuleOperator",
    "VisualCondition",
    "VisualRuleSet",
    "recover_visual_conditions",
]
