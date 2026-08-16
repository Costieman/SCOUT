"""Safe arithmetic and boolean expressions over named research features."""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from dataclasses import dataclass


class FeatureExpressionError(ValueError):
    """Raised when a feature expression is invalid or cannot be evaluated safely."""


class _Unavailable:
    """Typed sentinel for point-in-time feature values that are not available."""


_UNAVAILABLE = _Unavailable()


@dataclass(frozen=True, slots=True)
class CompiledFeatureExpression:
    """Validated expression tree restricted to deterministic feature arithmetic."""

    source: str
    allowed_names: frozenset[str]
    tree: ast.Expression

    def evaluate(self, values: Mapping[str, float | None]) -> bool:
        """Evaluate against one point-in-time feature row; unavailable inputs fail closed."""

        result = _evaluate_node(self.tree.body, values, self.allowed_names)
        if isinstance(result, _Unavailable):
            return False
        if not isinstance(result, bool):
            raise FeatureExpressionError("feature expression must evaluate to a boolean condition")
        return result


_MAX_EXPRESSION_LENGTH = 1_000
_MAX_AST_NODES = 100


def compile_feature_expression(
    source: str,
    *,
    allowed_names: frozenset[str],
) -> CompiledFeatureExpression:
    """Parse and validate a small expression language without calls, access, or mutation."""

    text = source.strip()
    if not text:
        raise FeatureExpressionError("feature expression must be non-empty")
    if len(text) > _MAX_EXPRESSION_LENGTH:
        raise FeatureExpressionError("feature expression is too long")
    if not allowed_names:
        raise FeatureExpressionError("allowed feature-name set must be non-empty")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FeatureExpressionError(f"invalid feature expression syntax: {exc.msg}") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise FeatureExpressionError("feature expression is too complex")
    _validate_node(tree.body, allowed_names)
    return CompiledFeatureExpression(source=text, allowed_names=allowed_names, tree=tree)


def _validate_node(node: ast.AST, allowed_names: frozenset[str]) -> None:
    if isinstance(node, ast.Name):
        if node.id not in allowed_names:
            raise FeatureExpressionError(f"unknown feature name {node.id!r}")
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FeatureExpressionError("only finite numeric constants are allowed")
        if not math.isfinite(float(node.value)):
            raise FeatureExpressionError("only finite numeric constants are allowed")
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
        _validate_node(node.operand, allowed_names)
        return
    if isinstance(node, ast.BinOp) and isinstance(
        node.op,
        (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow),
    ):
        _validate_node(node.left, allowed_names)
        _validate_node(node.right, allowed_names)
        return
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for child in node.values:
            _validate_node(child, allowed_names)
        return
    if isinstance(node, ast.Compare):
        for part in (node.left, *node.comparators):
            _validate_node(part, allowed_names)
        if not all(
            isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in node.ops
        ):
            raise FeatureExpressionError("unsupported comparison operator")
        return
    raise FeatureExpressionError(f"unsupported expression construct: {type(node).__name__}")


def _evaluate_node(
    node: ast.AST,
    values: Mapping[str, float | None],
    allowed_names: frozenset[str],
) -> float | bool | _Unavailable:
    if isinstance(node, ast.Name):
        feature_value = values.get(node.id)
        if feature_value is None:
            return _UNAVAILABLE
        numeric = float(feature_value)
        return numeric if math.isfinite(numeric) else _UNAVAILABLE
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FeatureExpressionError("only finite numeric constants are allowed")
        return float(value)
    if isinstance(node, ast.UnaryOp):
        operand_value = _evaluate_node(node.operand, values, allowed_names)
        if isinstance(operand_value, _Unavailable):
            return _UNAVAILABLE
        if isinstance(node.op, ast.Not):
            if not isinstance(operand_value, bool):
                raise FeatureExpressionError("not requires a boolean operand")
            return not operand_value
        numeric = _number(operand_value)
        return numeric if isinstance(node.op, ast.UAdd) else -numeric
    if isinstance(node, ast.BinOp):
        left_value = _evaluate_node(node.left, values, allowed_names)
        right_value = _evaluate_node(node.right, values, allowed_names)
        if isinstance(left_value, _Unavailable) or isinstance(right_value, _Unavailable):
            return _UNAVAILABLE
        return _binary(node.op, _number(left_value), _number(right_value))
    if isinstance(node, ast.BoolOp):
        evaluated: list[bool] = []
        for child in node.values:
            child_value = _evaluate_node(child, values, allowed_names)
            if isinstance(child_value, _Unavailable):
                return _UNAVAILABLE
            if not isinstance(child_value, bool):
                raise FeatureExpressionError("boolean operators require boolean operands")
            evaluated.append(child_value)
        return all(evaluated) if isinstance(node.op, ast.And) else any(evaluated)
    if isinstance(node, ast.Compare):
        left_value = _evaluate_node(node.left, values, allowed_names)
        if isinstance(left_value, _Unavailable):
            return _UNAVAILABLE
        current = _number(left_value)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            comparator_value = _evaluate_node(comparator, values, allowed_names)
            if isinstance(comparator_value, _Unavailable):
                return _UNAVAILABLE
            right = _number(comparator_value)
            if not _compare(operator, current, right):
                return False
            current = right
        return True
    raise FeatureExpressionError(f"unsupported expression construct: {type(node).__name__}")


def _number(value: float | bool) -> float:
    if isinstance(value, bool):
        raise FeatureExpressionError("arithmetic requires numeric operands")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise FeatureExpressionError("arithmetic produced a non-finite result")
    return numeric


def _binary(operator: ast.operator, left: float, right: float) -> float:
    try:
        if isinstance(operator, ast.Add):
            result = left + right
        elif isinstance(operator, ast.Sub):
            result = left - right
        elif isinstance(operator, ast.Mult):
            result = left * right
        elif isinstance(operator, ast.Div):
            result = left / right
        elif isinstance(operator, ast.Mod):
            result = left % right
        elif isinstance(operator, ast.Pow):
            result = left**right
        else:
            raise FeatureExpressionError("unsupported arithmetic operator")
    except (ArithmeticError, OverflowError) as exc:
        raise FeatureExpressionError(f"feature arithmetic failed: {exc}") from exc
    if not math.isfinite(result):
        raise FeatureExpressionError("feature arithmetic produced a non-finite result")
    return result


def _compare(operator: ast.cmpop, left: float, right: float) -> bool:
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    raise FeatureExpressionError("unsupported comparison operator")


__all__ = ["CompiledFeatureExpression", "FeatureExpressionError", "compile_feature_expression"]
