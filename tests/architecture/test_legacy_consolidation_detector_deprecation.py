"""Keep the exploratory consolidation detector out of production dependency paths."""

from __future__ import annotations

import ast
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _REPOSITORY_ROOT / "src" / "trade_scout"
_LEGACY_MODULE = "trade_scout.patterns.consolidation_breakout"
_DEPRECATED_EVENT_EXPORTS = frozenset(
    {
        "ConsolidationBreakoutEvent",
        "CurrentConsolidationState",
        "current_consolidation_state",
        "detect_consolidation_breakouts",
    }
)


def test_production_code_does_not_consume_legacy_consolidation_event_exports() -> None:
    violations: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if path == _PACKAGE_ROOT / "patterns" / "consolidation_breakout.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level != 0:
                continue
            if node.module != _LEGACY_MODULE:
                continue
            deprecated = sorted(
                alias.name for alias in node.names if alias.name in _DEPRECATED_EVENT_EXPORTS
            )
            if deprecated:
                relative = path.relative_to(_REPOSITORY_ROOT)
                violations.append(f"{relative}: {', '.join(deprecated)}")
    assert violations == [], (
        "legacy consolidation event APIs are compatibility-only; use trade_scout.events instead:\n"
        + "\n".join(violations)
    )
